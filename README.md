# ABI Maker - Autogenerate Python Web3 interfaces for Solidity contracts
If you have a JSON ABI for a Web3 project and the address it's deployed at, 
ABI Maker will create a minimal Python wrapper for the contracts you specify. 

## Installation
- *From PyPI:* 
  - `pip install abi_maker`

- *From Github:* (requires the [Poetry](https://python-poetry.org) package manager)
```shell
# (First, activate the virtualenv of your choice...)
source $PATH_TO_VENV/bin/activate
git clone git@github.com:Athiriyya/abi_maker.git
cd abi_maker
poetry install
# make_abi_wrapper has been added to your PATH
```

## Wrapper Generation
You can generate the wrapper from the command line with something like:

`make_abi_wrapper --project DFK --json DFK_ABIS.json`

## Python Wrapper Use
The created wrapper, placed on `$PYTHONPATH`, can then be used in Python:
```python

from DFK import all_dfk_contracts
hero_id = 68000
# Use contracts on the DFK Chain, in the the Crystalvale ('cv') realm
cv = all_dfk_contracts.AllDfkContracts(chain_key='cv')
# Use the same contracts on the Klaytn chain, in the Serendale ('sd') realm
sd = all_dfk_contracts.AllDfkContracts(chain_key='sd')

hero_tuple = cv.hero_core.get_hero(hero_id)
```


### ABI JSON Format
Here's a loose schema for a single-chain project .JSON file:
```json
{
  "PROJECT": "${YOUR_PROJECT_NAME}",
  "DEFAULT_RPC": "${SOME_URL}",
  "CONTRACTS":{
    "${CONTRACT_NAME}": {
      "ABI": [
        ${ABI_JSON_HERE}
      ],
      "ADDRESS": "${SOME_0X}"
    }
  }
}
```

And here's a multi-chain project file:
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

You can see example JSON files in Github [here](https://github.com/Athiriyya/abi_maker/tree/main/abi_maker/demo_abis).

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

## Questions or Suggestions
Leave issues or feature requests on [Github](https://github.com/Athiriyya/abi_maker/issues) or contact athiriyya@gmail.com