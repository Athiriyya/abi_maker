#! /usr/bin/env python
import json
import keyword
from pathlib import Path
import re
import shutil
from textwrap import indent, dedent

import inflection

from typing import Dict, List, Optional, Sequence, Tuple, Union, Callable, Any

HexAddress = str

INDENT = '    ' # 4 spaces. Changeable if you're a barbarian

PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / 'template_modules'

SNAKE_CASE_RE_1 = re.compile(r'(.)([A-Z][a-z]+)')
SNAKE_CASE_RE_2 = re.compile(r'([a-z0-9])([A-Z])')

# These functions, from OpenZeppelin's Access Control libraries or related to 
# Diamond storage, are not needed in the wrapper module. Unless there's a good 
# reason, we should exclude them from wrappers
INFRASTRUCTURE_FUNCTIONS = [
    'Initialized', 'Paused', 'Unpaused', 
    'initialize', 'paused', 'togglePause', 'unpause', 'pause', 
    'DiamondCut', 
    'diamondCut', 'facetAddress', 'facetAddresses', 'facetFunctionSelectors', 'facets',
    'RoleAdminChanged', 'RoleGranted', 'RoleRevoked', 
    'previousAdminRole', 'newAdminRole', 'getRoleAdmin', 'grantRole', 'hasRole', 
    'renounceRole', 'revokeRole', 'supportsInterface',
]

# FIXME: Function polymorphism is legal in Solidity but not in Python. 
# Having two functions, with the same name but different arguments A(arg1) & A(arg2, arg3) 
# is fine in Solidity but in Python will silently fail and only the last function
# will be valid.
# Proposal: number any duplicate-named functions (e.g. A(arg1), A1(arg2, arg3))

# See also: https://web3py.readthedocs.io/en/v5/contracts.html#invoke-ambiguous-contract-functions-example
# There's capacity to disambiguate functions based on their argument signatures,
# but I'm not sure how to incorporate that into this project
# - Athiriyya 12 January 2023

# (What I've done so far is just to manually remove the ABI JSON for duplicate-named functions)


# ===============
# = ENTRY POINT =
# ===============
def write_project_wrapper(project_name:str, abi_json_path:Path, output_dir:Path, overwrite_ok=False) -> List[Path]:
    if not abi_json_path.exists():
        raise ValueError(f"No ABI file present for project {project_name} at expected path {abi_json_path}")
    abis_by_name = json.loads(abi_json_path.read_text())

    # Make project dir, erasing any previous dir
    # Warn before overwriting a dir. If overwrite_ok is True, proceed.
    # project_dir = output_dir / project_name
    project_dir = output_dir 
    if project_dir.exists():
        overwrite_ok = overwrite_ok or yes_no_prompt(f'Overwrite project dir? ({project_dir})')
        if overwrite_ok:
            shutil.rmtree(project_dir)
        else:
            print(f'Refusing to overwrite project dir at {project_dir}. '
                  f'\nMove the directory or pass the -f command line option to continue')
            return []
    project_dir.mkdir(exist_ok=True)

    # Copy template modules into project dir
    [shutil.copy(template, project_dir / template.name) for template in TEMPLATES_DIR.iterdir()]

    # TODO: Customize superclass module; set default RPC, add anything else that's needed

    # Write a module for each contract in the JSON file
    module_paths = write_classes_for_abis(project_name, abis_by_name, project_dir)

    # Write a single class that imports & initializes all contract instances with specified RPC, etc
    # This is what a user will import & use
    all_contracts_path = write_all_contracts_wrapper(project_name, abis_by_name, module_paths, project_dir)

    # Write the ABI file to the package so there's evidence of how things were generated.
    shutil.copy(abi_json_path, project_dir / abi_json_path.name)

    return module_paths + [all_contracts_path]

def write_classes_for_abis( project_name:str, 
                            project_dict: Dict[str, Dict],
                            project_dir:Path ) -> List[Path]:
    written_paths:List[Path] = []

    contracts_dir =  project_dir / 'contracts'
    
    contracts_dir.mkdir(exist_ok=True, parents=True)

    # TODO: we might make some provisions for a customizable superclass    

    for contract_name, contract_info in project_dict['CONTRACTS'].items():
        # Note that this address may be a single hex address or a dict of addresses
        # for multi-chain contracts
        address = contract_info.get('ADDRESS')
        abi = contract_info['ABI']
        path = write_contract_wrapper_module(contract_name, abi, address, contracts_dir)
        written_paths.append(path)
    
    return written_paths

def write_contract_wrapper_module(contract_name:str, 
                                  contract_dicts:Sequence[Dict], 
                                  contract_address:Union[HexAddress, Dict[str, HexAddress]], 
                                  super_dir:Path) -> Path:

    abi_str = ',\n    '.join((json.dumps(d) for d in contract_dicts))
    abi_str = indent(abi_str, INDENT)

    multichain = isinstance(contract_address, dict)
    custom_contract = (contract_address is None or multichain and None in contract_address.values())

    superclass_name = 'ABIMultiContractWrapper' if custom_contract else 'ABIContractWrapper' 
    module_str = python_class_str_for_contract_dicts(contract_name, 
                                                contract_dicts, 
                                                contract_address, 
                                                abi_str,
                                                superclass_name)


    contract_path = (super_dir / to_snake_case(contract_name)).with_suffix('.py')
    contract_path.write_text(module_str)
    return contract_path

def write_all_contracts_wrapper(project_name:str, 
                                project_dict:Dict, 
                                contract_paths:Sequence[Path],
                                project_dir:Path) -> Path:
    init_strs = []
    import_strs = []

    contract_dicts = project_dict['CONTRACTS']
    # Figure out if this is a multichain contract
    single_dict:Dict = next(iter(contract_dicts.values()))
    is_multichain = isinstance(single_dict.get('ADDRESS'), dict)
    chain_arg = ''
    chain_type_arg = ''
    chain_self = ''
    if is_multichain:
        chain_arg = 'self.chain_key, '
        chain_type_arg = 'chain_key:str, '
        chain_self = '\n        self.chain_key = chain_key'

    default_rpc = project_dict.get('DEFAULT_RPC', None)

    for class_name, module_path in zip(contract_dicts.keys(), contract_paths):
        module_name = module_path.stem
        address_desc = contract_dicts[class_name]['ADDRESS']
        custom_contracts = ((is_multichain and not any(dict(address_desc).values()))
                            or (not is_multichain and not address_desc))
        # subclasses of AbiMultiContractWrapper (== ERC20, for now)
        # don't have a chain key or contract as part of their args
        chain_arg = '' if custom_contracts else 'self.chain_key, '

        import_strs.append(f'from .contracts.{module_name} import {class_name}')
        init_strs.append(indent(f'self.{module_name} = {class_name}({chain_arg}self.rpc)', INDENT*2))

    imports = '\n'.join(import_strs)
    inits = '\n'.join(init_strs)
    default_rpc_declaration = ''
    default_rpc_setting = ''
    if default_rpc:
        if isinstance(default_rpc, dict): 
            rpc_str = json_nest_dict_to_depth(default_rpc, 1)
            default_rpc_setting = ' or DEFAULT_RPC[chain_key]'
        else:
            rpc_str = f'"{default_rpc}"'
            default_rpc_setting = ' or DEFAULT_RPC'
        default_rpc_declaration = f'\nDEFAULT_RPC = {rpc_str}'

    class_str = dedent(
f'''
#! /usr/bin/env python

{imports}
{default_rpc_declaration}

class All{project_name.capitalize()}Contracts:
    # TODO: we might want to be able to specify other traits, like gas fees or timeout
    def __init__(self, {chain_type_arg}rpc:str | None = None):
        self.rpc = rpc{default_rpc_setting}{chain_self}

{inits}

'''
)

    all_contract_path = project_dir / f'all_{project_name.lower()}_contracts.py'
    all_contract_path.write_text(class_str)
    return all_contract_path

def python_class_str_for_contract_dicts(contract_name:str, 
                                        contract_dicts:Sequence[Dict], 
                                        contract_address:Union[None, HexAddress, Dict[str, HexAddress]],
                                        abi_str:str, 
                                        superclass_name:str = 'ABIContractWrapper' ) -> str:
    # There are two binary options for how we write contracts:
    # - contract may or may not be multichain, in which case CONTRACT_ADDRESS 
    #   is written as a dictionary rather than a single string, or
    # - contract may or may not be for an ERC20-style token, where a custom address
    #   is passed to every function call
    # 
    # We handle both circumstances below, but it's a little involved.    
    superclass_module = to_snake_case(superclass_name)

    # If contract_address is None/null, this is a token contract like ERC20
    # where the address of the token will be supplied as well as normal args, 
    # so a custom contract will be made for each call. 
    multichain = isinstance(contract_address, dict)
    custom_contract = (contract_address is None or multichain and None in contract_address.values())

    chain_type_arg = ''
    contract_setter = ''
    if multichain:
        address_str = indent(json.dumps(contract_address, indent=4), '    ' )
        address_str = address_str.replace('null', 'None')
        if not custom_contract:
            chain_type_arg = 'chain_key:str, '
            contract_setter = 'contract_address = CONTRACT_ADDRESS[chain_key]'
    else:
        address_str = 'None' if custom_contract else f'"{contract_address}"'

    custom_contract_init = dedent(f'''    def __init__(self, rpc:str):
                super().__init__(abi=ABI, rpc=rpc)
    ''')

    fixed_contract_init = dedent(f'''    def __init__(self, {chain_type_arg}rpc:str):
                {contract_setter}
                super().__init__(contract_address=contract_address, abi=ABI, rpc=rpc)
    ''')

    init_str = custom_contract_init if custom_contract else fixed_contract_init

    class_str = dedent(
    f'''
    from ..{superclass_module} import {superclass_name}
    from ..solidity_types import *
    from ..credentials import Credentials

    CONTRACT_ADDRESS = {address_str}

    ABI = """[
    {abi_str}
    ]
    """     

    class {inflection.camelize(contract_name)}({superclass_name}):
        {init_str}''')
    func_strs = [function_body(d, custom_contract) for d in contract_dicts]
    # remove empty strs
    func_strs = [f for f in func_strs if f]

    class_str += f'\n'.join(func_strs)
    return class_str

def function_body(function_dict:Dict, custom_contract=False) -> str:

    body = ''
    if function_dict['type'] != 'function':
        return body
    contract_func_name = function_dict.get('name')
    func_name = to_snake_case(contract_func_name)

    # Exclude functions for different reasons:
    # - Constructors have no 'name' field and we don't need a representation in Python; 
    # - Events also aren't callable; they'll be handled in a parse_events() method
    # - Lots of contracts have 5+ Role-related functions. We don't want these in a wrapper
    if (not contract_func_name 
        or function_dict['type'] == 'event'
        or 'role' in contract_func_name.lower()):
        return body


    solidity_args = [solidity_arg_name_to_pep_8(i['name']) for i in function_dict['inputs']]
    solidity_args = increment_empty_args(solidity_args, 'a')
    solidity_args_str = ', '.join(solidity_args)

    is_view = function_dict['stateMutability'] in ('view', 'pure')

    # We return 2 types of functions: contract function calls (views) & transactions,
    # and we return slightly different functions for standard contracts vs
    # currencies (like ERC20s) that create a contract object for each transaction
    def_func = function_signature(function_dict, custom_contract=custom_contract)
    if custom_contract:
        if is_view:
            body = dedent(f'''
            {def_func}
                contract = self.get_custom_contract(contract_address, abi=self.abi)
                return contract.functions.{contract_func_name}({solidity_args_str}).call()''')
        else:
            body = dedent(f'''
            {def_func}
                contract = self.get_custom_contract(contract_address, abi=self.abi)
                tx = contract.functions.{contract_func_name}({solidity_args_str})
                return self.send_transaction(tx, cred)''')
    else:
        if is_view:
            body = dedent(f'''
            {def_func}
                return self.contract.functions.{contract_func_name}({solidity_args_str}).call(block_identifier=block_identifier)''')
        else:
            body = dedent(f'''
            {def_func}
                tx = self.contract.functions.{contract_func_name}({solidity_args_str})
                return self.send_transaction(tx, cred)''')
    return indent(body, INDENT)

def solidity_arg_name_to_pep_8(arg_name:Optional[str]) -> str:
    # Note: some arg names are empty ("name":""). We depend
    # on the calling function to do something like `increment_empty_args()`
    # with the final list of arguments rather than handling that at this level
    PYTHON_ONLY_RESERVED_WORDS = keyword.kwlist
    snake_name = to_snake_case(arg_name)
    if snake_name in PYTHON_ONLY_RESERVED_WORDS:
        snake_name = '_' + snake_name
    return snake_name

def increment_empty_args(args:Sequence[str], incr_char='a') -> List[str]:
    args_out = []
    for a in args:
        if a:
            args_out.append(a)
        else:
            args_out.append(incr_char)
            incr_char = chr(ord(incr_char) + 1)
        
    return args_out

def function_signature(function_dict:Dict, custom_contract=False) -> str:
    # TODO: add type hints
    contract_func_name = function_dict['name']
    func_name = to_snake_case(contract_func_name)
    inputs = ['self']

    is_transaction = (function_dict['type'] == 'function' and function_dict['stateMutability'] in ('nonpayable', 'payable'))

    # Transactions require a Credentials argument to sign with; add it
    if is_transaction:
        inputs.append('cred:Credentials')
        return_type = ' -> TxReceipt'
    else:
        return_type = f' -> {get_output_types(function_dict["outputs"])}'

    if custom_contract:
        inputs.append('contract_address:address')

    substitute_arg_name = 'a'
    for arg_dict in function_dict['inputs']:
        arg_name = solidity_arg_name_to_pep_8(arg_dict['name'])
        if not arg_name:
            arg_name = substitute_arg_name
            substitute_arg_name = chr(ord(substitute_arg_name) + 1)
        arg_type = abi_type_to_hint(arg_dict, is_output=False)
        inputs.append(f'{arg_name}:{arg_type}')

    if not is_transaction:
        inputs.append(f"block_identifier:BlockIdentifier = 'latest'")

    inputs_str = ', '.join(inputs)

    sig = f'def {func_name}({inputs_str}){return_type}:'
    return sig

def get_output_types(outputs_list:Sequence[Dict]) -> str:
    if len(outputs_list) == 0:
        return 'None'
    else:
        if len(outputs_list) == 1:
            return abi_type_to_hint(outputs_list[0], is_output=True)
        else:
            out_types_str = ', '.join([abi_type_to_hint(o, is_output=True) for o in outputs_list])
            return f'Tuple[{out_types_str}]'

def abi_type_to_hint(arg_dict:Dict, is_output=False) -> str:
    type_in = arg_dict['type']
    
    # Figure out if this is a (possibly nested) list type
    bracket_pair_re = re.compile(r'\[\d*\]')
    list_depth = len(bracket_pair_re.findall(type_in))
    if list_depth > 0:
        match = bracket_pair_re.search(type_in)
        if match:
            type_in = type_in[:match.start()]

    # Nest lists as needed
    type_out = type_in
    for i in range(list_depth):
        if is_output:
            type_out = f'List[{type_out}]'
        else:
            type_out = f'Sequence[{type_out}]'

    return type_out

def to_snake_case(name:str | None = None) -> str:
    # See: https://stackoverflow.com/a/1176023/3592884
    # name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    # return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
    if not name:
        return ''
    name = SNAKE_CASE_RE_1.sub(r'\1_\2', name)
    return SNAKE_CASE_RE_2.sub(r'\1_\2', name).lower()

def is_infra_func(d:Dict) -> bool:
    return d.get('name') in INFRASTRUCTURE_FUNCTIONS

# ===========================
# = # DICT & ABI FORMATTING =
# ===========================
def write_abis_to_readable_file(abis:Dict[str, List[Dict]], abi_path:Path, exclude_role_funcs=True) -> Dict[str, List[Dict]]:
    # Write ABI JSON out in a way designed to be human-readable, 
    # neither all in one condensed line,
    # nor with every struct indented so it's hard to see the whole 
    # picture.
    # That structure looks like:
    # {
    #     "abi_contract_1": [
    #         {"dict_a": 1},
    #         {"dict_b": 1}
    #     ],

    #     "abi_contract_2": [
    #         {"etc": "etc"}
    #     ]
    # }
    
    # Also, order the entries in each ABI dict with name and type first
    ordered_abis = {k:make_ordered_dict(v, exclude_role_funcs) for k,v in abis.items()}
    out_str = '{\n' + ',\n\n'.join([f'"{k}":{one_dict_per_line(d)}' for k,d in ordered_abis.items()]) + '\n}' #type: ignore
    # TODO: I think this is a better way to nest dicts, but would need to test a little
    # out_str = json_nest_dict_to_depth(ordered_abis, flatten_after_level=3)
    abi_path.write_text(out_str)  
    print(f'Wrote ABI data to {abi_path}')
    return ordered_abis # type:ignore

def one_dict_per_line(dict_list:Sequence[Dict]) -> str:
    '''
    Render a list of dicts like so:
    [
        {'dict_a': 1},
        {'dict_b': 2}
    ]
    '''
    return f'[\n    ' + ',\n    '.join([json.dumps(d) for d in dict_list])  + '\n]'

def json_nest_dict_to_depth(elt:Union[Dict, List, Any], flatten_after_level=1, depth=0) -> Union[str, float]:
    # Return a json string, but with all elements deeper than flatten_after_level
    # on single lines:
    if depth > flatten_after_level:
        return json.dumps(elt)

    if isinstance(elt, dict):
        kv_strings = [f'"{k}": {json_nest_dict_to_depth(v, flatten_after_level, depth+1)}' for k, v in elt.items()]
        kvs = indent(',\n'.join(kv_strings), INDENT)
        return f'{{\n{kvs}\n}}'
    elif isinstance(elt, (list, tuple)):
        elts = [str(json_nest_dict_to_depth(e, flatten_after_level, depth+1)) for e in elt]
        es = indent(',\n'.join(elts), INDENT)
        return f'[\n{es}\n]'
    else:
        return json.dumps(elt)

def make_ordered_dict(d: Union[List, Dict], exclude_infra_funcs=True) -> Union[List, Dict]:
    # Given a dict or list of dicts, output a data structure with the same
    # contents, but with keys alphabetized and with the "name" field of any sub-dict
    # made first, so that ABI dicts are more easily readable.

    # exclude_role_funcs:  if True, don't include ABI functions that include the word 'role'
    # Lots of contracts use OpenZeppelin's role-access code, which includes about
    # 10 functions relating to roles which aren't usually usable by code clients,
    # so they clutter up ABIs. If requested, don't include these in the dicts we
    # output

    if not isinstance(d, (list, dict)):
        return d

    if isinstance(d, list):
        if exclude_infra_funcs:
            new_list = list([make_ordered_dict(d2, exclude_infra_funcs) for d2 in d if not is_infra_func(d2)])
        else:
            new_list = list([make_ordered_dict(d2, exclude_infra_funcs) for d2 in d])
        # Sort list entries alphabetically. In practice, this ends up sorting by
        # method names, which has the side effect of separating Solidity events 
        # (which start with a capital letter) from Solidity functions
        return sorted(new_list, key=lambda d:str(d))
        
    elif isinstance(d, dict):
        # Output a new dictionary with `priority_keys` first if present, 
        # then all other keys sorted alphabetically
        priority_keys = ['name', 'type', 'inputs', 'outputs']
        keys = set(d.keys())
        to_sort = keys - set(priority_keys)
        priorities_present = [k for k in priority_keys if k in keys]
        sorted_keys = priorities_present + sorted(to_sort)

        new_dict = {k:make_ordered_dict(d[k], exclude_infra_funcs) for k in sorted_keys}

    return new_dict

# ===========
# = HELPERS =
# ===========
def yes_no_prompt(prompt: str, default: bool = False) -> bool:
    default_str = 'Y/n' if default else 'y/N'
    res = input(f'{prompt} ({default_str}) ')
    if len(res) == 0:
        res = default_str
    result = res.lower() in ('yes', 'y')
    return result
