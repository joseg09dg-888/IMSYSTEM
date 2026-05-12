import sys, re
sys.stdout.reconfigure(encoding='utf-8')

c = open('frontend/index.html', encoding='utf-8').read()

# Buscar el div.main y ver su estructura exacta
idx = c.find('class="main"')
print('=== MAIN DIV ===')
print(c[idx:idx+500])

# Buscar el CSS del sidebar
sidebar_w = re.findall(r'--sidebar[^;]+;', c)
print('=== SIDEBAR VAR ===')
print(sidebar_w[:5])

# Ver margin-left del main
main_margin = re.findall(r'\.main[^{]*\{[^}]+\}', c)
print('=== MAIN CSS ===')
print(main_margin[:3])

# Ver si hay algún elemento con posicion fixed
fixed = re.findall(r'[^{]+\{[^}]*position:\s*fixed[^}]+\}', c)
print('=== FIXED ELEMENTS ===')
for f in fixed[:5]:
    print(f[:100])

# Extra: Ver que hay entre </body> y el primer panel
style_start = c.find('<style>')
style_end   = c.find('</style>')
css = c[style_start+7:style_end]

print()
print('=== POSIBLES CAUSAS DE DESPLAZAMIENTO ===')

# 1. margin/padding en body o html o main
for sel in ['html', 'body', '.main', '.content', '.panel']:
    matches = re.findall(rf'{re.escape(sel)}\s*\{{[^}}]+\}}', css)
    for m in matches:
        if any(k in m for k in ['margin', 'padding', 'top', 'height']):
            print(f'{sel}:', m[:150])

print()
print('=== TOPBAR height & sticky ===')
topbar_css = re.findall(r'\.topbar\s*\{[^}]+\}', css)
print(topbar_css)

print()
print('=== FS VAR USADA PERO NO DEFINIDA ===')
vars_definidas = re.findall(r'--([\w-]+)\s*:', re.search(r':root\s*\{([^}]+)\}', css).group(1))
vars_usadas    = set(re.findall(r'var\(--([\w-]+)\)', c))
rotas = [v for v in vars_usadas if v not in vars_definidas]
print('Vars rotas:', rotas)

print()
print('=== ELEMENTOS ENTRE BODY Y SIDEBAR ===')
body_pos   = c.find('<body')
aside_pos  = c.find('<aside')
between    = c[body_pos+6:aside_pos]
print(repr(between[:300]))

print()
print('=== ELEMENTOS ENTRE SIDEBAR Y MAIN ===')
aside_end = c.find('</aside>')
main_pos  = c.find('<div class="main"')
between2  = c[aside_end+8:main_pos]
print(repr(between2[:300]))
