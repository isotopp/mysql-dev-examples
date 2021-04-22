#! /bin/bash --

./mysql-commit-size.py drop
./mysql-commit-size.py create
for i in {5..14}
do
	csize=$((2 ** $i))
	./mysql-commit-size.py truncate
	echo "./mysql-commit-size.py fill --size=10000000 --commit-size=$csize"
	time ./mysql-commit-size.py fill --size=10000000 --commit-size=$csize
done
