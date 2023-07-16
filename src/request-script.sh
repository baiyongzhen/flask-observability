# sudo apt update -y
# sudo apt install siege -y
TIMES=1
for i in $(eval echo "{1..$TIMES}")
do
    siege -c 1 -r 10 http://localhost:5000/
    siege -c 3 -r 10 http://localhost:5000/io_task
    siege -c 2 -r 5 http://localhost:5000/cpu_task
    siege -c 5 -r 20 http://localhost:5000/random_sleep
    siege -c 2 -r 20 http://localhost:5000/random_status
    siege -c 2 -r 13 http://localhost:5000/chain
    siege -c 1 -r 5 http://localhost:5000/error_test
    sleep 5
done
