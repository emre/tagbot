import argparse
import json
import logging
import random
import time

from steem.post import Post

from tagbot.utils import get_steem_conn, get_current_vp, url, reputation

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


class TagBot:

    def __init__(self, config, steemd_instance):
        self.config = config
        self.steemd_instance = steemd_instance

    def check_vp(self):
        current_vp = get_current_vp(
            self.config["BOT_ACCOUNT"], self.steemd_instance)
        if current_vp < self.config["MINIMUM_VP_TO_START"]:
            raise ValueError(
                "Current voting power is not enough to start the round.",
                round(current_vp, 2)
            )
        else:
            logger.info("VP is enough, let's start the round!")

    def reputation_is_enough(self, author_rep):
        # if the user rep is below than 25, than discard the post.
        return reputation(author_rep) > self.config["MINIMUM_AUTHOR_REP"]

    def start_voting_round(self):
        # Fetch last 100 "hot" posts on the selected tag
        query = {"limit": 100, "tag": self.config["TAG"]}
        posts = list(self.steemd_instance.get_discussions_by_created(query))
        logger.info("%s posts found.", len(posts))

        # Discard the posts with authors low rep.
        posts = [p for p in posts if
                 self.reputation_is_enough(p["author_reputation"])]

        # Discard the posts with blacklisted authors
        blacklist = self.config.get("BLACKLIST", [])
        clear_posts = []
        skipped_authors = []
        for post in posts:
            if post.get("author") in blacklist:
                skipped_authors.append(post.get("author"))
                continue
            clear_posts.append(post)

        if len(skipped_authors):
            logger.info("These authors posts are skipped. \n %s", ",".join(skipped_authors))

        posts = clear_posts

        # Discard the posts with blacklisted tags
        tag_blacklist = self.config.get("TAG_BLACKLIST", [])
        clear_posts = []
        skipped_posts = []
        for post in posts:
            try:
                json_metadata = post.get("json_metadata")
                if json_metadata:
                    tags = json.loads(json_metadata)["tags"]
            except Exception as error:
                logger.error(error)
                skipped_posts.append(post)
                continue
            if len(set(tags).intersection(set(tag_blacklist))) > 0:
                skipped_posts.append(post)
                continue
            clear_posts.append(post)

        if len(skipped_posts):
            posts_as_identifier = [
                "%s/%s" % (p.get("author"), p.get("permlink"))
                for p in skipped_posts]
            logger.info(
                "These posts are skipped due to tag blacklist.\n %s",
                "\n".join(posts_as_identifier))

        posts = clear_posts
        logger.info("%s posts left after the filter.", len(posts))

        # Shuffle the list to make it random
        random.shuffle(posts)
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
