import argparse
import json
import logging
import random
import time
from datetime import datetime, timedelta

from dateutil.parser import parse
from steem.account import Account
from steem.post import Post

from tagbot.utils import get_steem_conn, get_current_vp, url, reputation, tokenize

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


class TagBot:

    def __init__(self, config, steemd_instance):
        self.config = config
        self.steemd_instance = steemd_instance

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

    def last_voted_accounts(self):
        voted_accounts = set()
        account = Account(self.config.get("BOT_ACCOUNT"))
        for vote in account.history_reverse(filter_by=["vote"]):
            created_at = parse(vote["timestamp"])
            if created_at < (datetime.utcnow() - timedelta(days=1)):
                break
            voted_accounts.add(vote["author"])

        return voted_accounts

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

    def start_voting_round(self):
        # Fetch last 100 posts on the selected tag
        query = {"limit": 100, "tag": self.config["TAG"]}
        posts = list(self.steemd_instance.get_discussions_by_created(query))
        logger.info("%s posts found.", len(posts))

        # Voted accounts in the last 24h
        already_voted = self.last_voted_accounts()

        blacklist = self.config.get("BLACKLIST", [])
        app_whitelist = self.config.get("APP_WHITELIST", [])
        filtered_posts = []
        for post in posts:
            post_instance = Post(post, steemd_instance=self.steemd_instance)

            if not self.reputation_is_enough(post["author_reputation"]):
                continue

            if post.get("author") in blacklist:
                continue

            if post.get("author") in already_voted:
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

            filtered_posts.append(post)

        logger.info("%s posts left after the filters." % len(filtered_posts))

        # Shuffle the list to make it random
        random.shuffle(filtered_posts)

        for post in posts[0:self.config["VOTE_COUNT"]]:
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
