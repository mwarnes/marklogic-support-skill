#!/bin/bash

# add to path as needed to find mlcp.sh
PATH=~/mlcp/bin:$PATH

# use:
# ./get-raw.sh localhost admin admin "2018-04-12T00:00:00" "2018-04-14T00:00:00"

host=$1
user=$2
pass=$3
# use format:  2018-03-14T00:00:00
start=$4
# use format:  2018-03-14T00:00:00
end=$5
# default, use the built-in server on port 8000
port=8000
# default output directory, should not exist before export
outdir=./meters-export


QUERY='{"andQuery":{"queries":[{"elementValueQuery":{"element":["{http://marklogic.com/manage/meters}period"], "text":["raw"], "options":["lang=en"]}}, {"elementRangeQuery":{"element":["{http://marklogic.com/manage/meters}period-start-time"], "operator":">", "value":[{"type":"dateTime", "val":"START"}], "options":["collation=http://marklogic.com/collation/"]}}, {"elementRangeQuery":{"element":["{http://marklogic.com/manage/meters}period-start-time"], "operator":"<", "value":[{"type":"dateTime", "val":"END"}], "options":["collation=http://marklogic.com/collation/"]}}]}}'
QUERY=${QUERY/START/$start}
QUERY=${QUERY/END/$end}

cat > .metrics <<!
-query_filter
$QUERY
!

cat .metrics
mlcp.sh export -host $host -port $port -username $user -password $pass -database Meters  -mode local -output_type archive -copy_permissions false -options_file .metrics -output_file_path=$outdir
