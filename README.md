# easydispatch

This is a field service dispatching planner, focusing on Reinforcement Learning and Optimization based automatic Dispatching. 

## Online Demo
We are working on demo.

## Problem Definition


## Quick Start
EasyDispatch relies on Postgres DB, Redis and Kafka. Those three components can be started by [docker-compose] (https://docs.docker.com/compose/install/) or provisioned seperately. You also should have [npm and node](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) for frontend development.

To run easydispatch locally, first install it by:
```bash
git clone https://github.com/alibaba/easydispatch.git && cd easydispatch
pip install -e .
```

Then open another terminal, populate some sample data and run the frontend:

```bash
python -m dispatch.cli database init
python -m dispatch.cli server start --port 8000 dispatch.main:app 
```

Visit the page at : http://localhost:8000/login

![planner_ui](doc/tutorial/planner_gantt_20210504215543.jpg)


### OS and Environements
We tested it on Ubuntu 20.04 and MacOS, Python 3.7 / 3.8


# Reference
The frontend and server technology stack (vue + python) were adapted from [Netflix Dispatch](https://github.com/Netflix/dispatch). Data structures are not compatible.


