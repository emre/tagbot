
import logging, random

from utils import get_steem_conn, get_current_vp, url, reputation
from settings import (
    BOT_ACCOUNT,
    MIN_VP_TO_START,
    TAG,
    MIN_AUTHOR_REP,
    POST_COUNT
)

from steem.post import Post

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


class DshotUpvoteBot:

    def __init__(self, steemd_instance, bot_account):
        self.steem = steemd_instance
        self.bot_account = bot_account

    def check_vp(self):
        current_vp = get_current_vp(self.bot_account, self.steem)
        if current_vp < MIN_VP_TO_START:
            raise ValueError(
                "Current voting power is not enough to start the round.",
                round(current_vp, 2)
            )
        else:
            logger.info("VP is enough, let's start the round!")

    def reputation_is_enough(self, author_rep):
        # if the user rep is below than 25, than discard the post.
        return reputation(author_rep) > MIN_AUTHOR_REP

    def start_voting_round(self):
        # Fetch last 100 "hot" posts on photography tag
        query = {"limit": 100, "tag": TAG}
        posts = list(self.steem.get_discussions_by_hot(query))
        logger.info("%s posts found.", len(posts))

        # Discard the posts with authors low rep.
        posts = [p for p in posts if
                 self.reputation_is_enough(p["author_reputation"])]

        logger.info("%s posts left after the filter.", len(posts))

        # Shuffle the list to make it random
        random.shuffle(posts)

        for post in posts[0:POST_COUNT]:
            self.upvote(Post(post, steemd_instance=self.steem))

    def upvote(self, post):
        # it should calculate the weight automatically.
        # it should check the active_votes to see it's already voted or not.
        # it should sleep 2 seconds after the vote
        # it should have a retry mechanism. It should retry broadcasting
        # the vote transaction up to N times. (3?)
        logger.info(url(post))

    def run(self):

        self.check_vp()
        self.start_voting_round()


if __name__ == '__main__':
    upvote_bot = DshotUpvoteBot(
        get_steem_conn(),
        BOT_ACCOUNT,
    )
    upvote_bot.run()