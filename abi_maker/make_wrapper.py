#! /usr/bin/env python

import argparse
from textwrap import indent, dedent
import json
import keyword
from pathlib import Path
import re
import shutil

import inflection

from typing import Dict, List, Optional, Sequence, Tuple, Union, Callable, Any

HexAddress = str



INDENT = '    ' # 4 spaces. Changeable if you're a barbarian
PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / 'template_modules'
PROJECTS_DIR = PACKAGE_DIR / 'projects'
PROJECTS_DIR.mkdir(exist_ok=True)

SNAKE_CASE_RE_1 = re.compile(r'(.)([A-Z][a-z]+)')
SNAKE_CASE_RE_2 = re.compile(r'([a-z0-9])([A-Z])')

def main():
    # args = parse_all_args()
    projects = [
        ('Evo', PACKAGE_DIR / 'EVO_ABIS.json'),
        ('DFK', PACKAGE_DIR / 'DFK_ABIS.json')
    ]
    for project_name, abi_json_path in projects:
        written_paths = write_project_wrapper(project_name, abi_json_path)
        print(f'Wrote {project_name} wrapper contracts at:')
        for p in written_paths: 
            print(p)

def write_project_wrapper(project_name:str, abi_json_path:Path) -> List[Path]:
    if not abi_json_path.exists():
        raise ValueError(f"No ABI file present for project {project_name} at expected path {abi_json_path}")
    abis_by_name = json.loads(abi_json_path.read_text())

    # Make project dir, erasing any previous dir
    project_dir = PROJECTS_DIR / project_name
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(exist_ok=True)

    # Copy template modules into project dir
    [shutil.copy(temp, project_dir / temp.name) for temp in TEMPLATES_DIR.iterdir()]

    # TODO: Customize superclass module; set default RPC, add anything else that's needed

    module_paths = write_classes_for_abis(project_name, abis_by_name)
    all_contracts_path = write_all_contracts_wrapper(project_name, abis_by_name, module_paths)
    return module_paths + [all_contracts_path]

def write_classes_for_abis( project_name:str, 
                            abis_by_name: Dict[str, Dict] ) -> List[Path]:
    written_paths:List[Path] = []

    contracts_dir = PROJECTS_DIR / project_name / 'contracts'
    contracts_dir.mkdir(exist_ok=True, parents=True)

    # TODO: we might make some provisions for a customizable superclass    
    # superclass_name = f'{project_name.capitalize()}Contract'
    superclass_name = 'ABIWrapperContract'
    for contract_name, contract_info in abis_by_name.items():
        address = contract_info['ADDRESS']
        abi = contract_info['ABI']
        path = write_contract_wrapper_module(contract_name, abi, address, superclass_name, contracts_dir)
        written_paths.append(path)
    
    return written_paths

def write_contract_wrapper_module(contract_name:str, contract_dicts:Sequence[Dict], contract_address:HexAddress, superclass_name:str, super_dir:Path) -> Path:

    # TODO: add named addresses for different networks, testnets, etc
    abi_str = ',\n    '.join((json.dumps(d) for d in contract_dicts))
    abi_str = indent(abi_str, INDENT)

    superclass_module = to_snake_case(superclass_name)
    module_str = python_class_str_for_contract_dicts(contract_name, 
                                                    contract_dicts, 
                                                    contract_address, 
                                                    abi_str,
                                                    superclass_module,
                                                    superclass_name)

    contract_path = (super_dir / to_snake_case(contract_name)).with_suffix('.py')
    contract_path.write_text(module_str)
    return contract_path

def write_all_contracts_wrapper(project_name:str, contract_dicts:Sequence[Dict], contract_paths:Sequence[Path]) -> Path:
    init_strs = []
    import_strs = []
    for class_name, module_path in zip(contract_dicts.keys(), contract_paths):
        module_name = module_path.stem
        # class_str += indent(f'self.{module_name} = contracts.{module_name}.{class_name}(self.rpc)\n', INDENT*2)
        import_strs.append(f'from .contracts.{module_name} import {class_name}')
        init_strs.append(indent(f'self.{module_name} = {class_name}(self.rpc)', INDENT*2))

    imports = '\n'.join(import_strs)
    inits = '\n'.join(init_strs)

    class_str = dedent(
f'''
#! /usr/bin/env python

{imports}

class All{project_name.capitalize()}Contracts:
    # TODO: we might want to be able to specify other traits, like gas fees or timeout
    def __init__(self, rpc:str=None):   
        self.rpc = rpc

{inits}

'''
)

    
    all_contract_path = PROJECTS_DIR / project_name / f'all_{project_name.lower()}_contracts.py'
    all_contract_path.write_text(class_str)
    return all_contract_path

def python_class_str_for_contract_dicts(contract_name:str, 
                                        contract_dicts:Sequence[Dict], 
                                        contract_address:Optional[HexAddress],
                                        abi_str:str, 
                                        superclass_module: str='abi_wrapper_contract',
                                        superclass_name:str = 'ABIWrapperContract' ) -> str:
    # If contract_address is None/null, this is a token contract like ERC20
    # where the address of the token will be supplied as well as normal args, 
    # so a custom contract will be made for each call. 
    custom_contract = (contract_address is None)
    address_str = 'None' if custom_contract else f'"{contract_address}"'

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

        def __init__(self, rpc:str=None):
            super().__init__(contract_address=CONTRACT_ADDRESS, abi=ABI, rpc=rpc)
    ''')
    func_strs = [function_body(d, custom_contract) for d in contract_dicts]
    # remove empty strs
    func_strs = [f for f in func_strs if f]

    class_str += f'\n'.join(func_strs)
    return class_str

def python_token_class_str_for_contract_dicts(contract_name:str, 
                                        contract_dicts:Sequence[Dict], 
                                        # contract_address:Optional[HexAddress],
                                        abi_str:str, 
                                        superclass_module: str='abi_wrapper_contract',
                                        superclass_name:str = 'ABIWrapperContract' ):
    # FIXME: if contract_address is None/null, this is a token contract like ERC20
    # where the address of the token will be supplied as well as normal args, 
    # so a custom contract will be made for each call. Make a couple small tweaks
    # to enable this.
    class_str = dedent(
    f'''
    from ..{superclass_module} import {superclass_name}
    from ..solidity_types import *
    from ..credentials import Credentials
    from web3.contract import Contract
    
    ABI = """[
    {abi_str}
    ]
    """     

    class {inflection.camelize(contract_name)}({superclass_name}):

        def __init__(self, rpc:str=None):
            super().__init__(contract_address=None, abi=ABI, rpc=rpc)

    ''')
    # FIXME: does this 
    func_strs = [function_body(d) for d in contract_dicts]
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

    #NOTE: make sure this covers all the bases we need. I'm assuming
    # that the only other option for 'stateMutability' is 'nonpayable', but I haven't verified this
    # - Athiriyya 21 November 2022
    is_view = function_dict['stateMutability'] in ('view', 'pure')

    # We return 2 types of functions: contract function calls & transactions,
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
                return self.contract.functions.{contract_func_name}({solidity_args_str}).call()''')
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
        arg_type = abi_type_to_hint(arg_dict)
        inputs.append(f'{arg_name}:{arg_type}')

    inputs_str = ', '.join(inputs)

    sig = f'def {func_name}({inputs_str}){return_type}:'
    return sig

def get_output_types(outputs_list:Sequence[Dict]) -> str:
    if len(outputs_list) == 0:
        return 'None'
    else:
        if len(outputs_list) == 1:
            return abi_type_to_hint(outputs_list[0])
        else:
            out_types_str = ', '.join([abi_type_to_hint(o) for o in outputs_list])
            return f'Tuple[{out_types_str}]'

def abi_type_to_hint(arg_dict:Dict) -> str:
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
        type_out = f'Sequence[{type_out}]'

    return type_out

def to_snake_case(name:str=None) -> str:
    # See: https://stackoverflow.com/a/1176023/3592884
    # name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    # return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
    if not name:
        return ''
    name = SNAKE_CASE_RE_1.sub(r'\1_\2', name)
    return SNAKE_CASE_RE_2.sub(r'\1_\2', name).lower()

def next_sibling_up_chain(elt):
    # I'm dealing with some inscrutably nested divs, with ~15 levels of nesting
    # for each row.
    '''
    <div>
        <div>
            <div>
                <div interesting-tag-here></div>
            </div>
        </div>
    </div>
    <div>
        <div>
            <div>
                <div other-tag-here></div>
            </div>
        </div>
    </div>
    
    '''
    # Given a node with 'interesting-tag-here', I want to look into the
    # the next div valley. I'm calling this 'next_sibling_up_chain'
    node = elt
    sibling = None
    while not sibling:
        sibling = node.next_sibling
        if not sibling:
            node = node.parent
    return sibling

def is_role_func(d:Dict) -> bool:
    # return ('role' in d.get('name', '') or d.get('name') == 'supportsInterface')    
    res = ('role' in d.get('name', '').lower() or d.get('name') == 'supportsInterface')    
    if not res:
        # print(f'is_role_func is False with dict: {d}')
        pass
    return res

# ===========================
# = # DICT & ABI FORMATTING =
# ===========================
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
        elts = [json_nest_dict_to_depth(e, flatten_after_level, depth+1) for e in elt]
        es = indent(',\n'.join(elts), INDENT)
        return f'[\n{es}\n]'
    else:
        return json.dumps(elt)

def make_ordered_dict(d: Union[List, Dict], exclude_role_funcs=True) -> Union[List, Dict]:
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
        if exclude_role_funcs:
            new_list = list([make_ordered_dict(d2, exclude_role_funcs) for d2 in d if not is_role_func(d2)])
        else:
            new_list = list([make_ordered_dict(d2, exclude_role_funcs) for d2 in d])
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

        new_dict = {k:make_ordered_dict(d[k], exclude_role_funcs) for k in sorted_keys}

    return new_dict

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

    out_str = '{\n' + ',\n\n'.join([f'"{k}":{one_dict_per_line(d)}' for k,d in ordered_abis.items()]) + '\n}'
    # TODO: I think this is a better way to nest dicts, but would need to test a little
    # out_str = json_nest_dict_to_depth(ordered_abis, flatten_after_level=3)
    abi_path.write_text(out_str)  
    print(f'Wrote ABI data to {abi_path}')
    return ordered_abis


def parse_all_args(args_in=None):
    ''' Set up argparser and return a namespace with named
    values from the command line arguments.  
    If help is requested (-h / --help) the help message will be printed 
    and the program will exit.
    '''
    program_description = '''Generate mimimal-boilerplate Python wrappers for Web3 contracts'''

    parser = argparse.ArgumentParser( description=program_description,
                formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Replace these with your arguments below
    # parser.add_argument( 'positional', help='A positional argument')
    # parser.add_argument( '-o', '--optional', type=int, help='An optional integer argument')

    # # If no arguments were supplied, print help
    # if len(sys.argv) == 1:
    #     sys.argv.append('-h')

    # If args_in isn't specified, args will be taken from sys.argv
    args_namespace = parser.parse_args(args_in)
    return args_namespace

if __name__ == '__main__':
    main()
