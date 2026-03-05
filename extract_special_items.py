import json, os, glob, collections

data_dir = 'C:/Users/jbharvey/Documents/poestash/poe_stash_data'
files = sorted(glob.glob(os.path.join(data_dir, 'tab_*.json')))

# Counters
uniques = collections.defaultdict(lambda: {'count': 0, 'typeLine': '', 'ilvl_set': set(), 'tabs': set(), 'frameType': 3})
gems = collections.defaultdict(lambda: {'entries': []})  # key = (name, level, quality)
currency = collections.defaultdict(int)
div_cards = collections.defaultdict(int)
other_special = collections.defaultdict(lambda: {'count': 0, 'frameType': 0, 'tabs': set()})

skipped = 0
processed = 0
total_items_checked = 0

for fpath in files:
    fname = os.path.basename(fpath)
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        skipped += 1
        continue

    tab_name = data.get('tab_name', fname)
    items = data.get('items', [])
    processed += 1
    total_items_checked += len(items)

    for item in items:
        ft = item.get('frameType', 0)
        if ft in (0, 1, 2):
            continue  # skip normal/magic/rare

        name = item.get('name', '')
        typeLine = item.get('typeLine', '')
        ilvl = item.get('ilvl', None)
        stackSize = item.get('stackSize', 1)
        if stackSize is None:
            stackSize = 1

        if ft == 3 or ft == 9:  # unique or foil unique
            key = name if name else typeLine
            uniques[key]['count'] += 1
            uniques[key]['typeLine'] = typeLine
            uniques[key]['frameType'] = ft
            if ilvl is not None:
                uniques[key]['ilvl_set'].add(ilvl)
            uniques[key]['tabs'].add(tab_name)

        elif ft == 4:  # gem
            # extract level and quality from properties
            gem_level = None
            gem_quality = None
            props = item.get('properties', [])
            for p in props:
                pname = p.get('name', '')
                if pname == 'Level':
                    vals = p.get('values', [])
                    if vals:
                        gem_level = vals[0][0]
                elif pname == 'Quality':
                    vals = p.get('values', [])
                    if vals:
                        gem_quality = vals[0][0]
            hybrid = item.get('hybrid', {})
            gem_name = name if name else typeLine
            if hybrid:
                hybrid_name = hybrid.get('baseTypeName', '')
                if hybrid_name:
                    gem_name = f"{gem_name} / {hybrid_name}"
            key = (gem_name, gem_level, gem_quality)
            gems[key]['entries'].append({'tab': tab_name, 'ilvl': ilvl})

        elif ft == 5:  # currency
            key = typeLine if typeLine else name
            currency[key] += stackSize

        elif ft == 6:  # divination card
            key = typeLine if typeLine else name
            div_cards[key] += stackSize

        elif ft == 7:  # quest item
            key = typeLine if typeLine else name
            other_special[key]['count'] += 1
            other_special[key]['frameType'] = ft
            other_special[key]['tabs'].add(tab_name)

        elif ft == 8:  # prophecy
            key = name if name else typeLine
            other_special[key]['count'] += 1
            other_special[key]['frameType'] = ft
            other_special[key]['tabs'].add(tab_name)

        else:
            key = f'[ft={ft}] {name or typeLine}'
            other_special[key]['count'] += 1
            other_special[key]['frameType'] = ft
            other_special[key]['tabs'].add(tab_name)

print(f'Processed {processed} tabs, skipped {skipped}')
print(f'Total items checked: {total_items_checked}')
print(f'Uniques: {len(uniques)}')
print(f'Gems: {len(gems)}')
print(f'Currency types: {len(currency)}')
print(f'Div cards: {len(div_cards)}')
print(f'Other special: {len(other_special)}')

# Save results
results = {
    'uniques': {k: {'count': v['count'], 'typeLine': v['typeLine'], 'frameType': v['frameType'], 'tabs': list(v['tabs'])} for k, v in uniques.items()},
    'gems': {str(k): {'count': len(v['entries']), 'entries': v['entries']} for k, v in gems.items()},
    'currency': dict(currency),
    'div_cards': dict(div_cards),
    'other_special': {k: {'count': v['count'], 'frameType': v['frameType'], 'tabs': list(v['tabs'])} for k, v in other_special.items()}
}

out_path = 'C:/poe/poe_special_items.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f'Results saved to {out_path}')
