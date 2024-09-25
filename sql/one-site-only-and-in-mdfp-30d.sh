#!/usr/bin/env bash

for line in $(sqlite3 badger.sqlite3 -batch -noheader 'SELECT tr.base, fqdn
  FROM site
  JOIN tracking t ON t.site_id = site.id
  JOIN tracker tr ON tr.id = t.tracker_id
  JOIN scan ON t.scan_id = scan.id
  WHERE scan.date <= DATETIME("now", "-30 day")
  GROUP by tr.id
  HAVING count(*) = 1
  ORDER BY tr.base ASC'); do

  tracker="$(echo "$line" | cut -d '|' -f 1)"
  if grep -q "$tracker" ../privacybadger/src/js/multiDomainFirstParties.js; then
    echo "$line";
  fi
done | column -s '|' -t
