#!/bin/sh
############################################################################
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You may have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307,
# USA.
#
# An on-line copy of the GNU General Public License can be found
# http://www.fsf.org/copyleft/gpl.html.
############################################################################
#
# log_processlist.sh (C) 2011-2015 Simon J Mudd <sjmudd@pobox.com>
#
# This script maintains a number of servers statistics in /var/log/mysql_pl.
#
# It is intended to be run every minute from cron, and takes no parameters
# as indicated below:
#
# * * * * * /usr/local/bin/log_processlist.sh
#
# It must run as root and will refuse to run if you try as a different
# user.
#
# Access to the db instances is currently exclusively done by looking for
# and then connecting to instances using defaults file matching the
# the following pattern: /root/.my.cnf.
#
# The script has been run successfully on MySQL versions 5.0, 5.1 and
# 5.5, 5.6 and 5.7.
#
# Running this script minutely from cron gives you a minutely overview of
# what the server and instances are doing and can be invaluable for
# debugging problems. Output includes the following information:
# - ps output for the server
# - SHOW FULL PROCESSLIST
# - SHOW SLAVE STATUS ( if the instance is a slave )
# - SHOW ENGINE INNODB STATUS (if the instance uses InnoDB)
#
# Files are dropped into /var/log/mysql_pl/XXX where XXX is (Mon,Tue,Wed,
# ...).  Each file is named according to the time of day and instance
# 'name', e.g. 15_30.
#
# Exit codes:
# 0 - all is fine.
# 1 - not started by root, refusing to run.
# 2 - there is no mysql command line client to be found.
# 3 - the required instance is not running (cannot be found in the process list).
# 4 - SQL failure
#
# Suggestions for improvement are always welcome and should be directed
# to me at the above email.

# pmp the mysqld when more than this many processes are in 'freeing items' state
pmp_threshold=30

[ -n "$DEBUG" ] && set -x
myname=$(basename $0)
lockfile=/tmp/$myname.lock
myuser=$(id -un)
myhome=$(getent passwd $myuser | cut -d: -f6)
myhostname=$(hostname -s)

# reference - get the day time in one go to avoid timing issues.
reference=$(date +%a_%H_%M)    # Mon_11_40  for Monday at 11:40 (unless locale is broken)
day_name=$(echo $reference | cut -d_ -f1)
current_time=$(echo $reference | cut -d_ -f2-3)

# We will drop stuff in $logdir/$day_name, and name it $logdir/$day_name/$current_time$suffix (with no dot)
logdir=/var/log/mysql_pl

# for cleaning up old format files.
warning_time=15_00

msg_info () {
	echo "$(date +'%b %d %H:%M:%S') $myhostname $myname[$$]: $*"
}

msg_verbose () {
	[ -n "$verbose" ] && msg_info "$*"
}

# add the uptime info
collect_system_info () {
	local log_file_base=$1
	local log_file=$log_file_base.unix

	echo 'DATE:'           >  $log_file 2>&1
	date                   >> $log_file 2>&1
	echo 'UPTIME:'         >> $log_file 2>&1
	uptime                 >> $log_file 2>&1
	echo 'UNIX_PROCESSES:' >> $log_file 2>&1
	ps auwwwx              >> $log_file 2>&1
	echo 'DISK SPACE:'     >> $log_file 2>&1
	df -Th                 >> $log_file 2>&1
	echo 'MEMORY:'         >> $log_file 2>&1
	free -m                >> $log_file 2>&1
	echo 'MEMORY:'         >> $log_file 2>&1
	free -m                >> $log_file 2>&1
	echo 'TMP TABLES:'     >> $log_file 2>&1
	du -m --time /mysql/*/tmp >> $log_file 2>&1

	${zipcmd} ${log_file} 2> /dev/null
}

#
# intended usage:
#   local pidfile=`fetch_value $my_cnf "select @@pid_file"`
#   local pid=`cat $pidfile`
#
fetch_value() {
	local my_cnf=$1
	shift

	mysql --defaults-file=$my_cnf --skip-column-names --batch --execute="$*"
}

try_sql () {
	local my_cnf=$1
	shift

	mysql --defaults-file=$my_cnf --silent --execute="$*" > /dev/null 2>&1
	return $?
}

# Run a mysql command and APPEND output to logfile
do_sql () {
	local logfile=$1
	local my_cnf=$2
	local sql=$3
	local filter=$4

	echo "SQL: $sql /* $(date) */" 2>&1 >> $logfile
	if [ -z "$filter" ]; then
		mysql --defaults-file=$my_cnf --batch --execute="$sql" 2>&1 >> $logfile
	else
		local cmd="mysql --defaults-file=$my_cnf --batch --execute=\"$sql\" 2>&1 | $filter"
		eval "$cmd" >> $logfile 2>&1
	fi
	local rc=$?
	if [ "$rc" -ne 0 ]; then
		echo "$myname: MySQL generates error $rc using defaults-file $my_cnf when executing: $sql"
		exit 4
	fi
}

check_processlist () {
	local logfile=$1
	local items

	if [ -f $logfile ]; then
		items=$(grep -c 'freeing items' $logfile)
		[ "$items" -ge "$pmp_threshold" ] && return 0 # true

		items=$(grep -c 'SHOW MASTER STATUS' $logfile)
		[ "$items" -ge "$pmp_threshold" ] && return 0 # true

		items=$(grep -c 'Query' $logfile)
		[ "$items" -ge "$pmp_threshold" ] && return 0 # true
	fi

	return 1 # false
}

collect_pmp_data() {
	local my_cnf=$1
	local logfile=$2
	shift 2

	logfile="$logfile.pmp"

	local pidfile=$(fetch_value $my_cnf "select @@pid_file")
	[ -z "$pidfile" ] && return   # no value
	[ ! -f $pidfile ] && return   # not a file

	local pid=$(cat $pidfile)
	[ -z "$pid" ] && return       # no pid

	msg_verbose "Collecting PMP information"

	# get a stack of all thread, and process it
	gdb -ex "set pagination 0" -ex "thread apply all bt" -batch -p $pid |\
	awk '
		BEGIN { s = ""; }
		/^Thread/ { print s; s = ""; }
		/^\#/ { if (s != "" ) { s = s "," $4} else { s = $4 } }
		END { print s } ' |\
			sort | uniq -c | sort -r -n -k 1,1 >> $logfile
}

# Collect the INNODB Engine status
# put this in a try block as some remote connections may not have SUPER privilege to run this.
collect_engine_innodb_status () {
	local my_cnf=$1
	local log_file=$2

	if try_sql $my_cnf 'SHOW ENGINE INNODB STATUS\G'; then
		(
			log_file=$log_file.innodb
			msg_verbose "my_cnf: $my_cnf - Adding INNODB STATUS to $log_file"
			do_sql $log_file $my_cnf 'SHOW ENGINE INNODB STATUS\G'
		)
	fi
}

# Get some InnoDB tables. Don't do this on FAV boxes as we've had crashes due to
# MySQL 5.6 bugs in 5.6.5, but enabled on other versions
collect_innodb_tables () {
	local my_cnf=$1
	local log_file=$2.innodb
	local mysql_version=$3
	# valid up to 8.0.1
	local i_s_innodb_locks=INFORMATION_SCHEMA.INNODB_LOCKS
	local i_s_innodb_lock_waits=INFORMATION_SCHEMA.INNODB_LOCK_WAITS

	# Queries on p_s data_locks seem to cause lockups on the server. Even with a 10s max_execution time
        # it locks for 30s while a large delete rows event is processed. This is on 8.0.12 on webmat
	# if echo "$mysql_version" | grep -q '^8\.0\.[1=9]'; then
	#	msg_verbose "my_cnf: $my_cnf - Collecting InnoDB transaction information from P_S tables"
	#	i_s_innodb_locks=performance_schema.data_locks
	#	i_s_innodb_lock_waits=performance_schema.data_lock_waits
	# else
        #	msg_verbose "my_cnf: $my_cnf - Collecting InnoDB transaction information from I_S tables"
	# fi

	# don't do the try for each select, just assume if this works so will the others...
	if try_sql $my_cnf 'SELECT COUNT(*) FROM INFORMATION_SCHEMA.INNODB_TRX'; then
		(
			msg_verbose "my_cnf: $my_cnf - Adding INNODB_TRX info to $log_file"
			do_sql $log_file $my_cnf 'SELECT /*+ MAX_EXECUTION_TIME(10000) */ * FROM INFORMATION_SCHEMA.INNODB_TRX'

			msg_verbose "my_cnf: $my_cnf - Adding INNODB lock info to $log_file"
			do_sql $log_file $my_cnf "SELECT /*+ MAX_EXECUTION_TIME(10000) */ * FROM $i_s_innodb_locks"

			msg_verbose "my_cnf: $my_cnf - Adding INNODB lock wait info to $log_file"
			do_sql $log_file $my_cnf "SELECT /*+ MAX_EXECUTION_TIME(10000) */ * FROM $i_s_innodb_lock_waits"

			# These 2 selects may work in 5.5 or 5.1+plugin only so do check here first
			if try_sql $my_cnf 'SELECT /*+ MAX_EXECUTION_TIME(10000) */ COUNT(*) FROM INFORMATION_SCHEMA.INNODB_CMP'; then
				msg_verbose "my_cnf: $my_cnf - Adding INNODB_CMP info to $log_file"
				do_sql $log_file $my_cnf 'SELECT /*+ MAX_EXECUTION_TIME(10000) */ * FROM INFORMATION_SCHEMA.INNODB_CMP'
				msg_verbose "my_cnf: $my_cnf - Adding INNODB_CMPMEM info to $log_file"
				do_sql $log_file $my_cnf 'SELECT /*+ MAX_EXECUTION_TIME(10000) */ * FROM INFORMATION_SCHEMA.INNODB_CMPMEM'
			fi
		)
	fi
	# Innodb metrics has some handy stats so collect this too.
	if try_sql $my_cnf 'SELECT /*+ MAX_EXECUTION_TIME(10000) */ * FROM INFORMATION_SCHEMA.INNODB_METRICS'; then
		(
			msg_verbose "my_cnf: $my_cnf - Adding INNODB_METRICS info to $log_file"
			do_sql $log_file $my_cnf 'SELECT /*+ MAX_EXECUTION_TIME(10000) */ * FROM INFORMATION_SCHEMA.INNODB_METRICS'
		)
	fi
	# Compress any log files.
	test -f $log_file && ${zipcmd} $log_file 2> /dev/null
}

# Show the uptime. Given changes in 5.7+ we need to check how to get this data out.
collect_uptime () {
	local mysql_version="$1"
	local my_cnf="$2"
	local log_file="$3"
	local table=INFORMATION_SCHEMA.GLOBAL_STATUS
	local show_compatibility_56=not_defined
	local mysql_80
	local query

	if echo "$mysql_version" | grep -qE '(5\.7|8\.0)'; then
		# exclude 8.0.0 DMR as that doesn't have this problem
		if echo "$mysql_version" | grep -q '8.0.[1-9]'; then
			mysql_80=1
		else
			show_compatibility_56=$(mysql --defaults-file=$my_cnf -BNe 'SELECT @@show_compatibility_56') ||\
				msg_fatal "$my_cnf: Unable to determine @@show_compatibility_56"
		fi
		# Check we can login to MySQL and get the version
		msg_verbose "show_compatibility_56: $show_compatibility_56"
		if [ "$show_compatibility_56" = 0 -o  -n "$mysql_80" ]; then
			table=performance_schema.global_status
		fi
	fi

	# DBR-10479, Collect MySQL uptime and record as this info can be useful.
	msg_verbose "my_cnf: $my_cnf - Adding uptime to $log_file"
	query='SELECT VARIABLE_VALUE FROM '$table' WHERE VARIABLE_NAME = "Uptime"'
	do_sql $log_file $my_cnf "$query"
}

# We now get the processlist and also the replication delay
collect_mysql_info () {
	local log_file_base=$1
	local my_cnf=$2
	local mysql_version

	# determine the suffix (which may be empty)
	local suffix=$(echo "$my_cnf" | sed -e 's,^.*/\.my,,' -e 's/\.cnf$//' -e 's/^-//')
	local log_file=${log_file_base}${suffix}

	# Look at the config file and if it's trying to talk to a socket
	# see if the instance is up. If not don't bother to try to even
	# connect to it. Note: we can't check for the full instance path as it might not match:
	# The path MAY be relative or absolute and may not include
	# the implicit $datadir prefix.  Don't bother to try and
	# be clever.
	if grep -q socket= $my_cnf; then
		config_socket=$(grep socket $my_cnf | sed -e "s/#.*//" -e 's/^ *socket *= *//' | tail -1)
		# originally we tried to find a mysqld in the processlist
		# which matches out $config_socket, but it is much more
		# complicated than that. For example, we might be talking
		# with $config_socket=/path/to/data/mysql.sock
		# but the server runs with
		#  --datadir=/path/to/data --socket=mysql.sock
		# and we will never find that out using grep.
		#
		# We try differently now:
		#   We attempt a connect, and if that works, all is fine.
		if [ -n "$config_socket" ]; then
			if ! mysql --defaults-file=$my_cnf -e 'SELECT 1' > /dev/null 2>&1; then
				return
			fi
		fi
	fi

	# Check we can login to MySQL and get the version
	mysql_version=$(mysql --defaults-file=$my_cnf -BNe 'SELECT @@VERSION' | cut -d- -f1) ||\
		msg_fatal "$my_cnf: Unable to determine MySQL version"
	msg_verbose "my_cnf: $my_cnf - Running MySQL version: $mysql_version"

	collect_uptime $mysql_version $my_cnf $log_file

	# Fetch processlist - use normal output so it's easier to filter the command
	# list from the shell when looking for long running queries.
	if [ "$show_processlist" = 1 ]; then
		if try_sql $my_cnf 'SELECT * FROM information_schema.processlist'; then
			msg_verbose "my_cnf: $my_cnf - Adding processlist info to $log_file"
			local perl_code='my ($s)=/\bIN\s*([(][^)]*)/i or next; my $n=()=$s=~/,/g; --$n>10 or next; 1 while s/\b(IN)\s*[(]\s*(\S+?),\s*(?:\S+?,\s*){2,}/$1 ($2, <count:$n>, /gi'
			local filter="perl -pe '$perl_code'"
			do_sql $log_file $my_cnf 'SELECT * FROM information_schema.processlist' "$filter"
		elif [ $current_time = $warning_time ]; then
			# To avoid spamming the world we only complain at 3 pm (arbitrary time)
			# and try to give a bit more info.

			cat <<-EOF
			WARNING: $myname

			MySQL generates error $rc using defaults-file $my_cnf when executing: SHOW FULL PROCESSLIST

			This is generally because the defaults file is missing an entry:
			socket=/path/to/data/mysql.sock

			Please check the config or remove the $my_cnf file.
			This warning will be repeated again at $(echo "$warning_time" | sed -e 's/_/:/').
			EOF
		fi
	else
		echo "SQL: SELECT * FROM information_schema.processlist - output disabled in /etc/my.cnf /* $(date) */" >> $log_file
	fi

	# set pmp flag if we should pmp the mysqld because of f-dip
	if check_processlist $log_file; then
		pmp=1
	else
		pmp=0
	fi

	# Check the replication delay.
	# - As we might not have the right grants we should first see if the command
	#   works and only if it works run it again and capture the output, this time
	#   to the end of the original config file.
	if try_sql $my_cnf 'SHOW SLAVE STATUS\G'; then
		msg_verbose "my_cnf: $my_cnf - Adding replication info to $log_file"
		do_sql $log_file $my_cnf 'SHOW SLAVE STATUS\G'
	fi
	# compress this
	test -f ${log_file}    && ${zipcmd} ${log_file} 2> /dev/null

	# Collect InnoDB information #################################################
	# - get the innodb status out but only if the engine is available

	HAVE_INNODB=$(fetch_value $my_cnf "SELECT SUPPORT FROM INFORMATION_SCHEMA.ENGINES WHERE ENGINE = 'InnoDB'")
	set -- $HAVE_INNODB
	# $1 = YES/DEFAULT
	HAVE_INNODB=$1

	case $HAVE_INNODB in
	YES|DEFAULT)
		collect_engine_innodb_status $my_cnf $log_file
		collect_innodb_tables        $my_cnf $log_file $mysql_version
		;;
	*)	msg_verbose "No InnoDB information to collect" ;; # do nothing
	esac

	GDB_BIN="$(which gdb 2>/dev/null)"
	if [ -f /usr/lib/debug/usr/sbin/mysqld.debug ]; then
		MYSQL_DEBUG=1
	fi
	if [ -n "$GDB_BIN" -a "$MYSQL_DEBUG" = "1" -a -f /var/run/enable_pmp -a "$pmp" = "1" ]; then
		collect_pmp_data $my_cnf $log_file
	fi
}

sanity_check () {
	local dir

	# This script currently assumes we have root privileges so check and give up if not.
	[ $myuser = root ] || {
		echo "$myname: This script is running as user $myuser and expects to be run as root."
		echo "- Please change the user or fix the script!"
		exit 1
	}
	msg_verbose "Checked that we are running as root"

	# If we are already running then exit
	cleanup_lockfile=0
	if [ -e $lockfile ]; then
		# Note: there's a race condition here between checking for the file, reading it and trying to get the pid.
		# It is possible that the file disappears in between so we have to take that into account.
		other_pid=$(sed -e 's/[ \t]//g' $lockfile 2>/dev/null)
		if [ $? = 0 ]; then
			if [[ -z $other_pid ]]; then
				msg_verbose "Lockfile exists, but failed to get other_pid. Exiting."
				exit 0
			fi
			if ps -p $other_pid >/dev/null; then
				msg_verbose "Another copy of this script appears to be running already with pid $other_pid. Exiting."
				exit 0
			fi
		fi
		# if the $? fails it means that the file has gone, so it should be ok to continue.
	fi

	# Keep the sysadmins happy.
	# - If no mysql binary can be found just exit.
	# mysqld on MySQL Community and Enterprise RPMS are normally in /usr/sbin
	# mysqld on RedHat system rpms are normally in /usr/libexec
	mysqld=
	mysqld_dirs='/usr/sbin /usr/libexec'
	for dir in $mysqld_dirs; do
		test -x $dir/mysqld && mysqld=$dir/mysqld
	done
	if [ -z "$mysqld" ]; then
		msg_verbose "Can not find mysqld in $mysqld_paths. Exiting"
		exit 2
	else
		msg_verbose "Found mysqld: $mysqld"
	fi

	# - If no mysql binary is running assume that the server is down and don't
	#   bother to try and query it. This avoids cron errors which upset us all.
	local count=$(ps -ef | grep $mysqld | grep -v grep | wc -l)
	if [ $count = 0 ]; then
		msg_verbose "No instances of mysqld have been found"
		exit 3
	fi
	msg_verbose "Checked that we can see at least one instance of mysqld running"

	cleanup_lockfile=1
	echo $$ > $lockfile
	msg_verbose "Checked that no other copy of this script is running"
}

# clean up the lockfile if asked to do this.
cleanup () {
	local rc=$?

	# This file is used to check for instance info.
	if [ -n "$instance_file" ]; then
		msg_verbose "Cleaning up instance_file: $instance_file"
		rm -f $instance_file
	fi

	if [ "$cleanup_lockfile" = 1 ]; then
		msg_verbose "Cleaning up lock file: $lockfile"
		[ -e $lockfile ] && rm -f $lockfile
	fi

	exit $rc
}

create_target_dir () {
	# check that the required target dir exists and if not, make it.
	# also drop a sensible README in there.
	local logdir=$1
	local day_name=$2

	if [ ! -d $logdir ]; then
		msg_verbose "creating missing directory $logdir"
		mkdir $logdir || exit 1
		cat <<-EOF > $logdir/README
		README
		======

		This directory contains the output of command $command run from
		script $myname which SHOULD be running every minute. Files are created
		in the subdirectories Mon, Tue, Wed, ... with the names according to
		the time in format hh_mm and a possible suffix according to the
		instance name.

		The script reads the instance configuration from ~/.my.cnf or ~/.my-XXX.cnf
		and generates output for each instance.  ~/.my-dba.cnf files are ignored.
		EOF
	fi

	# Create the directory for each day if needed.
	if [ ! -d $logdir/$day_name ]; then
		msg_verbose "Creating missing directory $logdir/$day_name"
		mkdir $logdir/$day_name || exit 1
	fi
}

# Should we show the full processlist output?
# Systems like MZ / FAV generate huge amounts of logging
# so this flag is to disable these collections. For now
# we look for the config indicator in /etc/my.cnf
# in the section as shown below:
#    [log_processlist_settings]
#    show_full_processlist = 0
#
# Rules:
# - no entry means we log as usual
# - show_full_processlist = 0 is the only sessing we use to disable logging.

# expected output will be 0 1 or nothing
want_full_processlist () {
	# this is not correct (not in the section we want) but will do.
	grep '^show_full_processlist' /etc/my.cnf |\
		sed -e 's/#.*//' \
			-e 's/^show_full_processlist[[:space:]]*=//' \
			-e 's/[[:space:]]//g'
}

# Sometimes we may have more than one .my-XXX file pointing to the same
# instance. This checks the instance by asking the @@hostname, @@datadir.
# if this has been seen before then we return 0, otherise 1. The instance
# information is stored in $instance_file which is cleaned up when the
# script exits.

seen_instance () {
	local instance_file=$1
	local my_cnf=$2
	local rc=1

	# Don't ask about this stupid CHAR(58). It's to avoid quotes inside try_sql
	# char(58) is ':'
	if try_sql $my_cnf 'SELECT CONCAT(@@hostname,CHAR(58),@@datadir)'; then
		instance_info=$(fetch_value $my_cnf 'SELECT CONCAT(@@hostname,CHAR(58),@@datadir)')
		grep -q $instance_info $instance_file
		rc=$?
		# We have not seen this instance before so add it to the list.
		if  [ $rc != 0 ] ; then
			msg_verbose "my_cnf: $my_cnf - NOT SEEN instance info $instance_info before"
			echo $instance_info >> $instance_file
		else
			msg_verbose "my_cnf: $my_cnf - HAVE SEEN instance info: $instance_info before, so ignoring"
		fi
	else
		msg_verbose "Unable to check for instance_info using defaults-file: $my_cnf"
	fi

	return $rc
}

zipcmd="gzip -9"
verbose=
while getopts vx flag; do
	case $flag in
	v)	verbose=1;;
	x)	zipcmd="xz";;
	*)	msg_info "Usage: $myname [-v] [-x]"
	esac
done

shift $(($OPTIND - 1))

msg_verbose "Running in verbose mode"

# Just in case we're upgrading mysql or the client has disappeared check to see
# if it's available. If it disappears then exit silently.
which mysql >/dev/null 2>&1 || exit 0

trap cleanup 0 1 2 3 9 15

sanity_check

# Create any missing directories if needed.
create_target_dir $logdir $day_name

log_file_base=$logdir/$day_name/$current_time
instance_file=$(mktemp -t $myname.XXXXXXXX)

# DBR-8211 Ensure we clean up _any_ data for this minute, so do it in 1 clear place.
rm -f ${log_file_base}*

# Get some more unix process info which is often handy.
# We now do this BEFORE getting the db output. If the db locks up we still have something to show.
collect_system_info $log_file_base

cd $myhome
my_cnf=$myhome/.my.cnf
if [ -e $my_cnf ]; then
	# check if we should not collect output of SHOW FULL PROCESSLIST
	show_processlist=$(want_full_processlist)
	test -z "$show_processlist" && show_processlist=1
	msg_verbose "show_processlist: $show_processlist"

	# the text LOG_PROCESSLIST: NO will stop us looking at this config file
	if ! grep -iq 'LOG_PROCESSLIST:[[:space:]]*NO' $my_cnf; then
		if ! seen_instance $instance_file $my_cnf; then
			collect_mysql_info $log_file_base $my_cnf
		fi
	fi
fi
