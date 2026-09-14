# Reasoning under Uncertainty — ProbLog Demo

An interactive causal network that computes your risk of missing a flight.
Built for Seminar Topic 3, 5DV244 Human-Centered AI, Umeå University.

## Run it
```
pip install problog
python main.py
```

## What it demonstrates

Pick your flight type, weather, transport, time buffer and so on — ProbLog
computes P(miss_flight) after every choice and the graph updates live.

- **Bayesian network** — the CPTs are written as ProbLog rules in `CausalRiskEngine`
- **Confounder** — weather affects the risk only through `traffic_delay`
- **do-operator** — choosing *Hotel (Day before)* removes the weather → delay
  path from the model entirely, so the weather stops mattering

Try it: set the weather to **Storm** with a taxi, then switch to **Hotel** and
click through all four weather options. The number stops moving — that is the
difference between observing and intervening.
