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
Here's a loose schema for a project .JSON file:
```json
{
  "PROJECT": "${YOUR_PROJECT_NAME}",
  "DEFAULT_RPC": {
    "${NETWORK_TAG_A}": "${SOME_URL}",
    "${NETWORK_TAG_B}": "${OTHER_URL}"
  }
  "CONTRACTS":{
    "${CONTRACT_NAME}": {
      "ABI": [
        ${ABI_JSON_HERE}
      ],
      "ADDRESS": {
        "${NETWORK_TAG_A}": "${SOME_0X}",
        "${NETWORK_TAG_B}": "${OTHER_0X}",
      } 
    }
  }
}
```

Note that, for single-network contracts, the values of "DEFAULT_RPC" and "ADDRESS"
may be single values rather than dictionaries. [Defi Kingdoms](https://defikingdoms.com/), as a multi-chain project, has: 
```json
  "DEFAULT_RPC": {
      "cv": "https://subnets.avax.network/defi-kingdoms/dfk-chain/rpc",
      "sd": "https://klaytn.rpc.defikingdoms.com/"
  },
```

While [The Beacon](https://www.thebeacon.gg/), only on Arbitrum, has:
```json
  "DEFAULT_RPC": "https://arb1.arbitrum.io/rpc"
```




### Alternate Superclasses