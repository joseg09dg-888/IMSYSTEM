import sys
sys.stdout.reconfigure(encoding='utf-8')
c = open('frontend/index.html', encoding='utf-8').read()

print('=== AUDITORIA COMPLETA ===')
print()

import re
paneles = re.findall(r'id="(p-[a-z_-]+)"', c)
nav_calls = re.findall(r"nav\('([^']+)'", c)
print('PANELES EXISTENTES:', paneles)
print('NAV CALLS:', sorted(set(nav_calls)))
print()

nav_sin_panel = [n for n in set(nav_calls) if 'p-'+n not in paneles]
panel_sin_nav = [p for p in paneles if p.replace('p-','') not in nav_calls]
print('NAV SIN PANEL (ROTO):', nav_sin_panel)
print('PANEL SIN NAV:', panel_sin_nav)
print()

funciones_llamadas = re.findall(r'onclick="([a-zA-Z_]+)\(', c)
funciones_definidas = re.findall(r'(?:function|async function)\s+([a-zA-Z_]+)\s*\(', c)
funciones_rotas = [f for f in set(funciones_llamadas) if f not in funciones_definidas]
print('FUNCIONES ROTAS (onclick sin definicion):', sorted(funciones_rotas))
print()

ids_en_js = re.findall(r"getElementById\('([^']+)'\)", c)
ids_en_html = re.findall(r'id="([^"]+)"', c)
ids_rotos = [i for i in set(ids_en_js) if i not in ids_en_html]
print('IDs EN JS SIN ELEMENTO HTML:', sorted(ids_rotos)[:30])
print()

fetch_urls = re.findall(r"fetch\('([^']+)'", c)
fetch_template = re.findall(r'fetch\(`([^`]+)`', c)
print('FETCH CALLS (static):', fetch_urls[:15])
print('FETCH CALLS (template):', fetch_template[:15])
print()

inputs_sin_id = len(re.findall(r'<input(?![^>]*id=)[^>]*>', c))
print('INPUTS SIN ID:', inputs_sin_id)
print()

botones_sin_onclick = len(re.findall(r'<button(?![^>]*onclick)[^>]*>', c))
print('BOTONES SIN ONCLICK:', botones_sin_onclick)
print()

clases_html = set(re.findall(r'class="([^"]+)"', c))
todas_clases = set()
for c_str in clases_html:
    todas_clases.update(c_str.split())
clases_css = set(re.findall(r'\.([-a-zA-Z_][-a-zA-Z0-9_]*)\s*\{', c))
clases_rotas = [cl for cl in todas_clases if cl not in clases_css and '-' in cl
                and not cl.startswith('text-') and not cl.startswith('bg-')]
print('CLASES CSS USADAS SIN DEFINICION:', sorted(clases_rotas)[:30])
print()

print('=== FIN AUDITORIA ===')
