# Monolith NFR Benchmark Results

## Monolith Architecture — Quantified NFR Benchmarks

| NFR | Metric | Monolith Value | Microservices Value | Winner |
|-----|--------|----------------|---------------------|--------|
| NFR-01 Performance | p95 latency `GET /dashboard/overview` | 520 ms (no cache) | 34 ms (cache hit) | Microservices |
| NFR-02 Scalability | Sustained throughput (RPS) | 154.69318401334735 RPS | 625.5809694019445 RPS | Microservices |
| NFR-03 Memory | RSS memory under load (single process) | 97.42 MiB (monolith total) | Distributed across 7 services | Monolith (base) |
| NFR-04 Fault Tolerance | Availability during service outage | 0% (entire app down) | 100% (stale cache) | Microservices |
| NFR-04 Recovery | MTTR after crash | 2.31 seconds | 2.02 seconds | Microservices |

## Locust Detailed Stats (Monolith)

### NFR-01 Response Time Stats
```
Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%
POST,/api/v1/auth/login,300,0,51,72.3019892067047,17.433720000553876,592.3793080000905,517.0,1.6624657502971927,0.0,51,63,78,96,120,190,300,570,590,590,590
POST,/api/v1/auth/register,300,0,94,187.81369974014524,46.808560997305904,1465.7283560009091,517.0,1.6624657502971927,0.0,95,110,140,250,470,650,1300,1400,1500,1500,1500
GET,GET /dashboard/overview (initial),300,0,54,107.64582533993234,18.31404899712652,730.4323349962942,141.0,1.6624657502971927,0.0,54,85,140,160,210,420,530,710,730,730,730
GET,GET /dashboard/overview (no cache),19529,0,18,93.65789994974959,5.9980340010952204,1731.5566140023293,141.0,108.22097879184626,0.0,18,26,45,91,320,520,740,890,1300,1700,1700
,Aggregated,20429,0,19,94.93237957828067,5.9980340010952204,1731.5566140023293,152.04312496940625,113.20837604273784,0.0,19,30,56,99,310,520,740,890,1300,1600,1700
```

### NFR-02 Throughput Stats
```
Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%
POST,/api/v1/auth/login,300,0,970.0,1479.48076884352,30.643787002190948,9211.51384300174,517.0,1.6589081395533227,0.0,980,1500,2200,2600,3900,4500,6000,7200,9200,9200,9200
POST,/api/v1/auth/register,300,0,2100.0,2989.618276186764,57.802424002147745,17016.60169800016,517.0,1.6589081395533227,0.0,2100,3600,4500,4900,6500,8800,11000,12000,17000,17000,17000
GET,GET /dashboard/overview,20623,0,320.0,899.1259937578609,9.429181001905818,16478.75125099381,1793.779614992969,114.03887520669392,0.0,320,540,1000,1300,2300,3500,5100,6600,11000,15000,16000
POST,POST /transactions/manual,6752,0,380.0,951.0035007726607,18.200860999058932,16158.895233995281,98.0,37.33649252754678,0.0,380,580,1100,1300,2400,3500,5400,6800,12000,16000,16000
,Aggregated,27975,0,340.0,940.2888550489519,9.429181001905818,17016.60169800016,1357.1050223413763,154.69318401334735,0.0,340,590,1100,1400,2400,3700,5500,6900,12000,16000,17000
```

## Comparison with Microservices

| NFR | Metric | Microservices | Monolith | Ratio |
|-----|--------|:------------:|:--------:|:-----:|
| NFR-01 | p95 Latency (ms) | 34 | 520 | 15.3x slower |
| NFR-02 | Throughput (RPS) | 625.5809694019445 | 154.69318401334735 | 4.0x higher |
| NFR-03 | Memory (MiB) | Distributed | 97.42 | — |
| NFR-04 | Fault Tolerance | 100% available | 0% (total failure) | ∞ |
| NFR-04 | MTTR (seconds) | 2.02 | 2.31 | 1.1x slower |
