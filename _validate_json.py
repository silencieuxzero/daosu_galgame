import json

with open(r'e:\MaiBot\plugins\daosu_galgame\data\plot\xaviel\xaviel_05.json', encoding='utf-8') as f:
    data = json.load(f)

node_count = len(data['nodes'])
print(f'Valid JSON. Node count: {node_count}')

choices_count = sum(len(n.get('choices', [])) for n in data['nodes'].values() if 'choices' in n)
print(f'Total choices: {choices_count}')

# Count emotions used
emotions = {}
for n in data['nodes'].values():
    e = n.get('emotion', '')
    emotions[e] = emotions.get(e, 0) + 1
print(f'Emotions used: {emotions}')

# Check all next_node references are valid
all_node_keys = set(data['nodes'].keys())
for node_id, node in data['nodes'].items():
    if 'next_node' in node and node['next_node'] is not None:
        if node['next_node'] not in all_node_keys:
            print(f'ERROR: Node "{node_id}" references non-existent next_node "{node["next_node"]}"')
    if 'choices' in node:
        for i, choice in enumerate(node['choices']):
            if choice['next_node'] not in all_node_keys:
                print(f'ERROR: Node "{node_id}" choice {i} references non-existent next_node "{choice["next_node"]}"')

# Check affection_change ranges
for node_id, node in data['nodes'].items():
    if 'choices' in node:
        for i, choice in enumerate(node['choices']):
            aff = choice.get('affection_change', 0)
            if aff < 0 or aff > 10:
                print(f'WARNING: Node "{node_id}" choice {i} affection_change {aff} out of range 0-10')

# Check characters
for node_id, node in data['nodes'].items():
    if node.get('speaker') not in ('narrator', '查维尔'):
        print(f'ERROR: Node "{node_id}" has unknown speaker "{node.get("speaker")}"')

print('\nAll checks passed!' if True else '')
