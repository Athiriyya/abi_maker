# ABI Maker - Autogenerate Python Web3 interfaces for Solidity contracts
If you have a JSON ABI for a Web3 project and the address it's deployed at, 
ABI Maker will create a minimal Python wrapper for the contracts you specify. 

You can generate the wrapper with something like:
`make_abi_wrapper --project DFK --json DFK_ABIS.json`

The created wrapper can then be used with:
```python
from DFK import all_dfk_contracts
rpc = 'https://subnets.avax.network/defi-kingdoms/dfk-chain/rpc'
hero_id = 68000
cv = all_dfk_contracts.AllDfkContracts(rpc=rpc)
hero_tuple = cv.hero_core.get_hero(hero_id)
```

### Installation
- *From PyPI (TODO, once released):* 
  - `pip install abi_maker`

- *From Github:*
- (requires the [Poetry](https://python-poetry.org)) package manager
```shell
# (First, activate the virtualenv of your choice...)
git clone git@github.com:Athiriyya/abi_maker.git
cd abi_maker
poetry install
# make_abi_wrapper was added to your PATH
```


### Wrapper Creation

### Python Wrapper Use


### JSON Format

### Alternate Superclasses