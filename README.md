# Virtual-Hedge-Fund
Virtual Hedge Fund Project for Final Year Project 

1. **Prerequisites**

   Ensure you have the following installed on your system:
   - [**Docker**](https://www.docker.com/products/docker-desktop/) - The #1 containerization software for developers and teams
   - [**Node.js**](https://nodejs.org/en/download/) - JavaScript runtime environment
   - [**poetry**](https://python-poetry.org/docs/#installation) - Python dependency management and packaging tool

2. **Clone the repository:**


3. **Set up environment variables:**

   Create your local dev environment file by copying the example provided:

   ```sh
   cp .env.example .env
   ```

   This `.env` file will configure the app for development using the provided default values.

4. **Install dependencies:**

   Run the following to install all dependencies:

   ```sh
   poetry install
   ```

5. **Set up Docker containers:**

   Ensure Docker is running, then execute:

   ```sh
   poetry run poe up-all
   ```

   This will spin up the required Docker containers configured in the `docker-compose` file.


6. **Set up QuantRocket Environment:**

Ensure you have an account
https://www.quantrocket.com/account/

Activate your license:
https://www.quantrocket.com/docs/#deploy-license-key

```python
from quantrocket.license import set_license
set_license("XXXXXXXXXXXXXXXX")
```

Ensure history is created

```python
from quantrocket.history import create_usstock_db
from quantrocket.history import collect_history

create_usstock_db("usstock-free-1d", bar_size="1 day", free=True)
collect_history("usstock-free-1d")
```

Ensure universe is created

```python
from quantrocket.master import get_securities
from quantrocket.history import list_sids
from quantrocket.master import create_universe

free_sids = list_sids("usstock-free-1d")
securities = get_securities(sids=free_sids)
create_universe("usstock-free", sids=securities.index.tolist())
```
