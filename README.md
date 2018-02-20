### tagbot

Tagbot is a upvote bot, upvotes posts with a specific tag based on pre-defined parameters. 
It has a couple use cases, for example:

- Voting for photography tag to support photographers
- Voting for local tags (tr, deutsch, etc.) to support local content creators
- Voting for the "utopian-io" tag to support developers

etc. 

#### Installation

```
$ (sudo) pip install steem_tagbot
```

Do that in a python3.6 virtual environment and it will install all the requirements.

#### Running

```
$ POSTING_KEY=private_posting_key tagbot /path/to/config.json
```

Configuration is stored in JSON files. You can find an example in the repository.

|        Option       | Value                                                |
|:-------------------:|------------------------------------------------------|
| NODES               |  A list of steem nodes to connect                    |
| BOT_ACCOUNT         | Bot account to vote                                  |
| TAG                 | Target tag to upvote posts                           |
| MINIMUM_VP_TO_START | Bot should sleep until this VP is generated          |
| VOTE_WEIGHT         | Vote weight for every upvote (in percent)            |
| VOTE_COUNT          | How many votes should be casted in each voting round |
| MINIMUM_AUTHOR_REP  | Ignore authors with low reputation                   |
| BLACKLIST           | A list of authors to ignore                          |
