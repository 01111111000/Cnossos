"""Extract the complete unresolved configuration register, preserving exact text."""
from pathlib import Path


def render(path='config/main.yaml'):
    rows=[]
    for n,line in enumerate(Path(path).read_text().splitlines(),1):
        if 'TK' in line or 'TODO(' in line:
            rows.append(f'{n}: {line}')
    return '# Open configuration questions\n\nEvery line below remains unresolved for live execution.\n\n```yaml\n'+'\n'.join(rows)+'\n```\n'


if __name__=='__main__': print(render(),end='')
