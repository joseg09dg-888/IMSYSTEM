import csv, glob

empresas_files = [f for f in glob.glob('data/leads_*_20260917_*.csv') if 'artista' not in f]
todos = []
for f in empresas_files:
    rows = list(csv.DictReader(open(f, encoding='utf-8')))
    todos.extend(rows)

con_email = [r for r in todos if r.get('email', '').strip()]
sin_email = [r for r in todos if not r.get('email', '').strip()]

fieldnames = list(todos[0].keys())
with open('data/CONSOLIDADO_empresas_medellin.csv', 'w', newline='', encoding='utf-8') as out:
    w = csv.DictWriter(out, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(sorted(todos, key=lambda r: (r.get('email', '') == '', r.get('nicho', ''))))

print(f'TOTAL: {len(todos)} leads')
print(f'CON EMAIL (listos para mandar ya): {len(con_email)}')
print(f'SIN EMAIL (solo nombre/tel): {len(sin_email)}')
print()
print('=== Los que SI tienen email ===')
for r in con_email:
    nicho = r['nicho']
    empresa = r['empresa'][:40]
    email = r['email']
    print(f'  [{nicho:16s}] {empresa:40s} {email}')
