import argparse
import json
import logging
import random
import time
from datetime import datetime, timedelta

from dateutil.parser import parse
from steem.account import Account
from steem.post import Post
from steem.amount import Amount

from tagbot.utils import get_steem_conn, get_current_vp, url, reputation, tokenize

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


class TagBot:

    def __init__(self, config, steemd_instance):
        self.config = config
        self.steemd_instance = steemd_instance
        self.target_tags = config.get("TAGS") or [config.get("TAG"), ]

    def check_vp(self):
        current_vp = get_current_vp(
            self.config["BOT_ACCOUNT"],
            self.steemd_instance)
        if current_vp < self.config["MINIMUM_VP_TO_START"]:
            raise ValueError(
                "Current voting power is not enough to start the round.",
                round(current_vp, 2)
            )
        else:
            logger.info("VP is enough, let's start the round!")

    def last_voted_accounts_and_posts(self):
        voted_accounts = set()
        voted_posts = set()
        account = Account(self.config.get("BOT_ACCOUNT"))
        vote_interval = self.config.get("VOTE_INTERVAL_IN_DAYS", 1)
        for vote in account.history_reverse(filter_by=["vote"]):
            created_at = parse(vote["timestamp"])
            if created_at < (datetime.utcnow() - timedelta(days=vote_interval)):
                break
            voted_accounts.add(vote["author"])
            voted_posts.add("@%s/%s" % (vote["author"], vote["permlink"]))

        return voted_accounts, voted_posts

    def conforms_minimum_word_count(self, body):
        # @todo: consider removing noise. (html, markdown etc.)
        if self.config.get("MINIMUM_WORD_COUNT"):
            word_count = len(tokenize(body))
            if word_count < self.config.get("MINIMUM_WORD_COUNT"):
                return False
        return True

    def reputation_is_enough(self, author_rep):
        # if the user rep is below than 25, than discard the post.
        return reputation(author_rep) > self.config["MINIMUM_AUTHOR_REP"]

    def fetch_tag(self, tag, start_author=None, start_permlink=None, posts=None, scanned_pages=None):

        logger.info("Fetching tag: #%s", tag)

        if not scanned_pages:
            scanned_pages = 0

        if not posts:
            posts = []

        query = {
            "limit": 100,
            "tag": tag,
        }
        if start_author:
            query.update({
                "start_author": start_author,
                "start_permlink": start_permlink,
            })
        post_list = list(self.steemd_instance.get_discussions_by_created(query))
        for post in post_list:
            created_at = parse(post["created"])

            if (datetime.utcnow() - created_at).days > 5:
                return posts

            elapsed_hours = (datetime.utcnow() - created_at).total_seconds() // 3600
            if self.config.get("MINIMUM_POST_AGE"):
                if self.config.get("MINIMUM_POST_AGE") > elapsed_hours:
                    continue

            if self.config.get("MAXIMUM_POST_REWARDS"):
                pending_payout = Amount(post.get("pending_payout_value"))
                if pending_payout.amount > self.config.get("MAXIMUM_POST_REWARDS"):
                    continue

            posts.append(post)

        if scanned_pages > 300 or len(posts) > 100:
            logger.info("%s posts found at #%s tag.", len(posts), tag)
            return posts

        # empty tag?
        if not len(post_list):
            return posts

        return self.fetch_tag(
            tag,
            start_author=post["author"],
            start_permlink=post["permlink"],
            posts=posts,
            scanned_pages=scanned_pages + 1,
        )

    def start_voting_round(self):
        posts = []
        for tag in self.target_tags:
            posts += self.fetch_tag(tag)
        logger.info("%s posts found.", len(posts))

        already_voted_accounts, already_voted_posts = self.last_voted_accounts_and_posts()

        blacklist = self.config.get("BLACKLIST", [])
        app_whitelist = self.config.get("APP_WHITELIST", [])
        filtered_posts = []
        for post in posts:
            post_instance = Post(post, steemd_instance=self.steemd_instance)

            if not self.reputation_is_enough(post["author_reputation"]):
                continue

            if "@%s/%s" % (post.get("author"), post.get("permlink")) in already_voted_posts:
                continue

            if post.get("author") in blacklist:
                continue

            if post.get("author") in already_voted_accounts:
                continue

            tag_blacklist = self.config.get("TAG_BLACKLIST", [])
            if set(tag_blacklist).intersection(post_instance.get("tags")):
                continue

            if app_whitelist:
                app = post_instance.get("json_metadata").get("app")
                if not app:
                    continue
                app_without_version = app.split("/")[0]
                if app_without_version not in app_whitelist:
                    continue

            if not self.conforms_minimum_word_count(post_instance.get("body")):
                continue

            if self.config.get("TRUSTED_ACCOUNTS"):

                # check downvotes
                found_downvote = False
                for vote in post.get("active_votes", []):
                    rshares = vote["rshares"]
                    if not isinstance(rshares, int):
                        rshares = int(rshares)

                    if vote["voter"] in self.config.get("TRUSTED_ACCOUNTS") and rshares < 0:
                        found_downvote = True
                        break

                if found_downvote:
                    logger.info("Found a downvote of trusted accounts. Skipping. %s", post.identifier)
                    continue

            filtered_posts.append(post)

        logger.info("%s posts left after the filters." % len(filtered_posts))

        # Shuffle the list to make it random
        random.shuffle(filtered_posts)

        for post in filtered_posts[0:self.config["VOTE_COUNT"]]:
            if self.config.get("DEBUG"):
                print(post)
                continue

            # check cheetah commented on it
            replies = self.steemd_instance.get_content_replies(
                post.get("author"), post.get("permlink")
            )

            found_cheetah = False
            for reply in replies:
                if reply["author"] in ["cheetah"]:
                    found_cheetah = True
                    break

            if found_cheetah:
                logger.info(
                    "Post: %s is skipped since it's commented by cheetah.",
                    post.identifier
                )
                continue

            self.upvote(
                Post(post, steemd_instance=self.steemd_instance),
                self.config["VOTE_WEIGHT"]
            )

    def upvote(self, post, weight, retry_count=None):

        if not retry_count:
            retry_count = 0

        if self.config["BOT_ACCOUNT"] in [
            v["voter"] for v in post.get("active_votes", [])]:
            logger.error(
                "Already voted on this. Skipping. %s", post.identifier)
            return

        try:
            self.steemd_instance.commit.vote(
                post.identifier,
                weight, account=self.config["BOT_ACCOUNT"])
            logger.info(
                "Casted vote on: %s with weight: %s", url(post), weight)
            time.sleep(3)

        except Exception as error:
            logger.error(error)
            return self.upvote(post, weight, retry_count + 1)

        if self.config.get("POST_REPLY_TEMPLATE"):
            self.reply(post)

    def reply(self, post):
        reply_template = open(self.config.get("POST_REPLY_TEMPLATE")).read()

        reply_body = reply_template.format(
            author=post.get("author")
        )
        post.reply(reply_body, author=self.config["BOT_ACCOUNT"])
        time.sleep(20)

    def run(self):
        self.check_vp()
        self.start_voting_round()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Config file in JSON format")
    args = parser.parse_args()
    config = json.loads(open(args.config).read())
    upvote_bot = TagBot(
        config,
        get_steem_conn(config["NODES"])
    )
    upvote_bot.run()


if __name__ == '__main__':
    main()
