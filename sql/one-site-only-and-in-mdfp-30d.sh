#"/usr/bin/env bash

for line in $(sqlite3 badger.sqlite3 -batch -noheader "SELECT t.base,
    GROUP_CONCAT(DISTINCT s.fqdn)
  FROM tracking tr
  JOIN site s ON s.id = tr.site_id
  JOIN tracker t ON t.id = tr.tracker_id
  JOIN scan ON scan.id = tr.scan_id
  WHERE scan.start_time <= DATETIME('now', '-30 day')
  GROUP BY t.base
  HAVING COUNT(*) == 1
  ORDER BY t.base ASC"); do

  tracker="$(echo "$line" | cut -d '|' -f 1)"
  if grep -q "\"$tracker\"" ../privacybadger/src/js/multiDomainFirstParties.js; then
    echo "$line";
  fi
done | column -s '|' -t
