#! /bin/bash --

./mysql.py drop
./mysql.py create
for i in {5..14}
do
	csize=$((2 ** $i))
	./mysql.py truncate
	echo "./mysql.py fill --size=100000 --commit-size=$csize"
	time ./mysql.py fill --size=100000 --commit-size=$csize
done
