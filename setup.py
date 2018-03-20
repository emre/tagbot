from setuptools import setup

setup(
    name='steem_tagbot',
    version='0.0.3',
    packages=["tagbot",],
    url='http://github.com/emre/tagbot',
    license='MIT',
    author='emre yilmaz',
    author_email='mail@emreyilmaz.me',
    description='Random upvote bot on specific tags on steem network',
    entry_points={
        'console_scripts': [
            'tagbot = tagbot.bot:main',
        ],
    },
    install_requires=["steem_dshot",]
)
