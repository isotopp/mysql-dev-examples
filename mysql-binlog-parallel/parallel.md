	
> Assuming an infinite set of replication appliers, how many of those can I keep busy given a particular binlog position?
> That is, what is the degree of parallelism in the binlog stream at a given position, and how can I find that out?

Each transaction contains two logical timestamps, `sequence_number` and `last_committed`.

`sequence_number` is an identifier for the transaction and is unique within the binary log file.
`last_committed refers` to the most recent earlier transaction in this binary log that the source server that generated this binary log assumes might be conflicting.

Therefore, when the replica applier schedules transaction `T`, it waits for the transaction having sequence number `T.last_committed` to commit, and then be scheduled.
Thus, `T` can execute in parallel with at most `T.sequence_number - T.last_committed - 1` earlier transactions.

The parallelism is additionally limited because transactions are scheduled in sequence.
The scheduler will not even look at the transaction until it has scheduled all the preceding transactions.

Therefore, `T` will implicitly wait for `T'.last_committed` for all `T'` such that `T.last_committed < T'.sequence_number < T.sequence_number`.
So a closed formula for the maximum possible parallelism for transaction `T` is

```
max(T'.last_committed : T.last_committed < T'.sequence_number <= T.sequence_number)
```

These logical timestamps are printed by `mysqlbinlog`:
There is a comment at the beginning of each GTID event (or Anonymous_GTID event) containing the text `last_committed=X sequence_number=Y`.
So to find the maximum possible parallelization for a given transaction:

- run `mysqlbinlog ... | grep "last_committed=.* sequence_number=.*"`
- find the line corresponding to the transaction you are looking for, suppose it has `last_committed=X sequence_number=Y`
- get the list of values for `last_committed` among all the transactions having `X<sequence_number<=Y` (note: the transaction itself is included).
- Find the maximal value for last_committed among those `Y-X` transactions, call it `Z`.
- The applier is guaranteed to wait for the transaction having `sequence_number=Z` to commit,
  and in case there are sufficiently many workers will be able to schedule it in parallel 
  with `Y-Z-1` preceding transactions.

> I know about the config variables `binlog_dependency_tracking` and `replica_parallel_type`,
> but where exactly in the manual is a writeup on how exactly parallel replication works in
> the various scenarios (guarantees, ordering, etc)? 
> Ch 17 Replication does not really discuss it.

Thank you for pointing this out.
Unfortunately this is not documented in detail.
Our engineering team has shared the following text:

This text describes how source servers compute and represent dependencies between transactions,
which are used by the multi-threaded applier on the replica side to determine which transactions can execute in parallel.

Servers with binary logs enabled track dependencies between transactions.
Dependent transactions, also known as conflicting transactions, will not be scheduled to execute in parallel on the replica.
Independent / non-conflicting transaction may execute in parallel on the replica.

# How dependencies are represented

Transaction dependencies are represented in the binary log using logical timestamps.
Every transaction is equipped with two logical timestamps:
`sequence_number` and `last_committed`. 
For brevity we denote them `SN` and `LC` henceforth.
`SN` identifies the transaction; 
it is `1` for the first transaction in the binlog, `2` for the second one, and so on, always monotonically increasing, generated once the order is known. 
`LC` refers to an earlier transaction: 
it is the `SN` of the most recent earlier transaction that this transaction depends on.

Example: Suppose we have three transactions:

```console
T1: sn=5 lc=4
T2: sn=6 lc=5
T3: sn=7 lc=5
T4: sn=8 lc=6
```

This says that `T2` depends on `T1`, `T3` depends on `T1`, `T4` depends on `T2`.

The replica applier will schedule `T1`, then wait for `T1` to commit until it schedules `T2`, then let `T3` execute in parallel witih `T2`, then wait for `T2` to commit before it schedules `T4`.

# How dependencies are generated

There are several policies for generating the logical timestamps, configured with `binlog_transaction_dependency_tracking`.
The available policies are `COMMIT_ORDER`, `WRITESET`, and `WRITESET_SESSION`.

## COMMIT_ORDER

The idea of `COMMIT_ORDER` can be described and understood in several alternative ways.
We first describe the underlying idea, based on a certain time interval in the transaction's life cycle.
Transactions are considered independent if their respective time intervals overlap.
Then, we describe how we compute the logical timestamps in order to realize this scheme.
Then, we describe a different version of `COMMIT_ORDER`, which was implemented in very early versions of the feature and does not provide as good parallelization as the current scheme.

### Time-window description

For each transaction, we define the `all_locks_time_window`, which is a time interval that begins after the last statement of the transaction before the commit, and ends just before the storage engine commit.

Example 1: Consider the following transaction:

```
BEGIN;
INSERT;
UPDATE;
COMMIT;
```

The `all_locks_time_window` begins after `UPDATE` and ends at a point in time during the execution of `COMMIT` that occurs just before storage engine commit (`ha_commit_low`).

Example 2: Consider the following transaction:

```
SET auto_commit=1;
INSERT;
```

The `all_locks_time_window` begins at a point in the transaction commit pipeline just before storage engine prepare and ends just before storage engine commit.

We declare that two transactions are non-conflicting when their respective `all_locks_time_windows` overlap in time.

Transactions that are declared to be non-conflicting according to this algorithm, are guaranteed to never contend on a lock, 
as long as both guarantee (1) that lock is not released before storage engine commit,
and (2) that lock is not acquired after the last statement.

The first requirement is guaranteed for locks that obey two-phase locking.
The second requirement is assumed to hold in practice in MySQL because there is no reason to take a lock when no statement is executed.

### Description of logical timestamp computation

When using `bCOMMIT_ORDER`, `LC` is computed for a transaction `T` prior to the commit.
At the end of each statement in `T`, the server sets `T.LC` to the value of `SN` for the most recently committed transaction.
(We track this by updating a global variable each time a transaction commits; 
just before ha_commit is called in the storage engine(s).)

Thus, when `T` commits, `T.LC` will have the value of the most recent transaction that was committed at the time the last statement of `T` ended.

Therefore, every transaction after `T.LC` is not-yet-committed at that point. 
Therefore, `SN` marks the beginning of the `all_locks_time_window`, and the `all_locks_time_window` for `T` overlaps with the `all_locks_time_window` for every transaction committed after `T.LC` and before `T`.

## WRITESET

When `WRITESET` is used, the server computes a set of integers for each transaction:
for each row in the transaction, and for each unique key in the table, we add an integer to the set which is equal to the hash ("checksum") of the key values for that row.
This set of numbers is called the transaction's writeset.

Two transactions are declared to be `writeset-independent` if their writesets are disjoint.
When `WRITESET` is configured, transactions are considered independent if they are writeset-independent or if they are independent acording to `COMMIT_ORDER`.

We compute writeset-independence as follows.
Writesets are accumulated during the transaction execution, so at the time the transaction is going to commit, the writeset is ready.

We maintain a global map object called `writeset_history`, where keys are hashes and values are the SN of some transaction.
When a transaction has entered the commit queue, so that its `SN` is known, we compute writeset-independence.
First, we lookup each entry in the transaction's writeset in the `writeset_history`; the largest number we find will be the `LC` for the transaction, according to the writeset-independence logic.
Then, we update the map by setting `writeset_history[H]=T.SN`, for each `H` in the transaction's writeset.
Finally, we also compare the `LC` computed using `COMMIT_ORDER` with the `LC` computed using writesets, and use the smallest of them.

The `writeset_history` has a fixed capacity, and when it gets full, it is cleared.
It is also cleared in several other cases, where transaction dependencies cannot currently be correctly determined based on writesets.
This includes DDLs, foreign keys, and other cases.

Whenever the `writeset_history` is reset, the next transaction to commit does not know anything about the history, and has to assume that it depends on all previous transactions.
Therefore, this may result in a "serialization point" for the replica applier:
that transaction has to wait for all previous transactions to commit, before it can start to execute.

In such cases, the use of the `LC` computed by the `COMMIT_ORDER` algorithm can at least provide a little parallelism across the writeset reset point.
This is the main reason why we combine the two algorithms.

# OLD_COMMIT_ORDER

This describes an old feature that has been removed from the server.

In early versions of the `COMMIT_ORDER` feature, the logic was different.
There was only one logical timestamp per transaction, and it was an identifier of the commit group that the transaction belongs to.
Thus, all transactions in the first commit group had their logical timestamps set to 1; all transactions in the next commit group had 2, and so on.

The replica would parallelize transactions only if they had the same logical timestamps.

This provides significantly less parallelization than the current `COMMIT_ORDER` that uses two logical timestamps. 
This can be understood, for instance, in terms of time windows.

We can define `old_commit_order_time_window` as the time from when a transaction enters group commit until it is written to the binary log.
`OLD_COMMIT_ORDER` parallelizes two transactions only if their `old_commit_order_time_windows` overlap.

Since `old_commit_order_time_window` is strictly shorter than `all_locks_time_window`, there is a smaller chance for two transactions to have overlapping time windows when using `OLD_COMMIT_ORDER`.

Moreover, `COMMIT_ORDER` makes it possible for the replica's parallel applier to have a continuous `load of >= K` parallel transactions, since this scheme makes it is possible that all transactions have `LC < SN - K`.

On the other hand, with `OLD_COMMIT_ORDER`, the first transaction in commit group `N+1` has to wait for every previous transaction to commit, before it can be scheduled.

Therefore, it exhibits frequent 'serialization points', where there is no parallelization at all.
