# Aiohttp Scanner

A Python 3.5+ script that uses aiohttp to find text in list of sites asynchronously.

## Requirements

* Python >= 3.5.3
* [aiohttp](https://pypi.python.org/pypi/aiohttp)
* [async-timeout](https://pypi.python.org/pypi/async_timeout)

## Usage
1. Put your urls list in data/urls.txt
2. Put your paths list in data/paths.txt
3. Configure settings in data/config/config.json
    ```
    timeout - request operations timeout (default 30)
    threads - count of threads (default 10)
    save_every_time - how often to save progress (default 100)
    refresh_connector_every_time - how often to refresh tcp connections (default 1000)
    time_waiting_while_refresh - how long to wait while connector refreshing (default 120 seconds)
    break_on_good - break scanning current site when finding a good result (default true)
    max_timeouts - maximum quantity of timeouts per site (default 5)
    user_agent - user-agent
    contentFind - text to be found on site
    ```
4. Run `$ python scanner`