# marshmallow dashboard

marshmallow download stats, visualized.

## why?

To make more informed decisions about which marshmallow and Python versions to support. But mostly cuz graphs are fun.

## developing locally

```
cp .env.example .env

docker-compose up
```

This will use static data by default. To use data from BigQuery, change the credentials in your `.env` file and set `USE_STATIC_DATA` to `false`.

## license

[MIT Licensed](https://sloria.mit-license.org/).
