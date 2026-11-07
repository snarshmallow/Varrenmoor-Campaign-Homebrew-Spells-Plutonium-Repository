#!/bin/sh
# usage: runjob.sh <abs job file> -> copies into illustrator/jobs and waits for the result (named after the job's id)
f="$1"
cd "$(dirname "$0")/../.."
id=$(python -c "import json,sys;print(json.load(open(sys.argv[1]))['id'])" "$f")
rm -f jobs/done/$id.result.json
cp "$f" jobs/$id.json
for i in $(seq 1 28); do [ -f jobs/done/$id.result.json ] && break; sleep 4; done
python -c "
import json;d=json.load(open('jobs/done/$id.result.json'));print('ok',d['ok']);[print(r) for r in d['results'] if not r.get('ok')]"
