## clearing redis on heroku

```
heroku redis:cli -a marshmallow-dashboard -c marshmallow-dashboard
flushall
```
