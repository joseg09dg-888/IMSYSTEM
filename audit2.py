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
for f in fixed[:8]:
    print(f[:120])
    print()
