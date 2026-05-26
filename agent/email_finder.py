
import os, requests, time
from dotenv import load_dotenv
load_dotenv(override=True)

# ═══════════════════════════════════
# CONFIGURACIÓN DE APIS
# ═══════════════════════════════════
APOLLO_KEY   = os.environ.get('APOLLO_API_KEY', '')
HUNTER_KEY   = os.environ.get('HUNTER_API_KEY', '')
SKRAPP_KEY   = os.environ.get('SKRAPP_API_KEY', '')
SNOV_ID      = os.environ.get('SNOV_CLIENT_ID', '')
SNOV_SECRET  = os.environ.get('SNOV_CLIENT_SECRET', '')


def buscar_email_hunter(nombre, dominio):
    if not HUNTER_KEY: return None
    try:
        r = requests.get(
            'https://api.hunter.io/v2/email-finder',
            params={
                'domain': dominio,
                'first_name': nombre.split()[0] if nombre else '',
                'last_name': nombre.split()[-1] if len(nombre.split()) > 1 else '',
                'api_key': HUNTER_KEY
            }, timeout=10
        )
        d = r.json().get('data', {})
        email = d.get('email', '')
        score = d.get('score', 0)
        if email and score > 50:
            return {'email': email, 'score': score, 'fuente': 'hunter'}
    except: pass
    return None


def verificar_email_hunter(email):
    if not HUNTER_KEY: return None
    try:
        r = requests.get(
            'https://api.hunter.io/v2/email-verifier',
            params={'email': email, 'api_key': HUNTER_KEY},
            timeout=10
        )
        d = r.json().get('data', {})
        return {
            'valido': d.get('status') in ['valid', 'accept_all'],
            'score': d.get('score', 0),
            'fuente': 'hunter'
        }
    except: return None


def buscar_email_skrapp(nombre, empresa):
    if not SKRAPP_KEY: return None
    try:
        partes = nombre.split()
        r = requests.post(
            'https://api.skrapp.io/api/v2/find',
            json={
                'firstName': partes[0] if partes else '',
                'lastName': partes[-1] if len(partes) > 1 else '',
                'linkedInUrl': '',
                'company': empresa
            },
            headers={
                'X-Access-Key': SKRAPP_KEY,
                'Content-Type': 'application/json'
            }, timeout=10
        )
        d = r.json()
        email = d.get('email', '')
        if email:
            return {'email': email, 'fuente': 'skrapp'}
    except: pass
    return None


def get_snov_token():
    if not SNOV_ID or not SNOV_SECRET: return None
    try:
        r = requests.post(
            'https://api.snov.io/v1/oauth/access_token',
            data={
                'grant_type': 'client_credentials',
                'client_id': SNOV_ID,
                'client_secret': SNOV_SECRET
            }, timeout=10
        )
        return r.json().get('access_token', '')
    except: return None


def buscar_email_snov(nombre, dominio):
    token = get_snov_token()
    if not token: return None
    try:
        partes = nombre.split()
        r = requests.post(
            'https://api.snov.io/v1/get-emails-from-names',
            json={
                'firstName': partes[0] if partes else '',
                'lastName': partes[-1] if len(partes) > 1 else '',
                'domain': dominio
            },
            headers={'Authorization': f'Bearer {token}'},
            timeout=10
        )
        emails = r.json().get('emails', [])
        if emails:
            return {'email': emails[0].get('email', ''), 'fuente': 'snov'}
    except: pass
    return None


def buscar_email_apollo(nombre, empresa, dominio=''):
    if not APOLLO_KEY: return None
    try:
        r = requests.post(
            'https://api.apollo.io/v1/people/match',
            json={
                'first_name': nombre.split()[0] if nombre else '',
                'last_name': nombre.split()[-1] if len(nombre.split()) > 1 else '',
                'organization_name': empresa,
                'domain': dominio
            },
            headers={
                'Cache-Control': 'no-cache',
                'Content-Type': 'application/json',
                'X-Api-Key': APOLLO_KEY
            }, timeout=10
        )
        person = r.json().get('person', {})
        email = person.get('email', '')
        if email and 'apollo.io' not in email:
            phone = ''
            phones = person.get('phone_numbers', [])
            if phones:
                phone = phones[0].get('sanitized_number', '')
            return {
                'email': email,
                'telefono': phone,
                'linkedin': person.get('linkedin_url', ''),
                'fuente': 'apollo'
            }
    except: pass
    return None


def buscar_telefono_whatsapp(nombre, empresa, pais='CO'):
    if not APOLLO_KEY: return None
    try:
        r = requests.post(
            'https://api.apollo.io/v1/people/match',
            json={
                'first_name': nombre.split()[0] if nombre else '',
                'last_name': nombre.split()[-1] if len(nombre.split()) > 1 else '',
                'organization_name': empresa,
                'country': pais
            },
            headers={
                'Cache-Control': 'no-cache',
                'Content-Type': 'application/json',
                'X-Api-Key': APOLLO_KEY
            }, timeout=10
        )
        person = r.json().get('person', {})
        phones = person.get('phone_numbers', [])
        if phones:
            return {
                'telefono': phones[0].get('sanitized_number', ''),
                'tipo': phones[0].get('type', 'mobile'),
                'fuente': 'apollo'
            }
    except: pass
    return None


def buscar_dominio_empresa(empresa, ciudad=''):
    if not HUNTER_KEY: return None
    try:
        r = requests.get(
            'https://api.hunter.io/v2/domain-search',
            params={
                'company': empresa,
                'api_key': HUNTER_KEY,
                'limit': 3
            }, timeout=10
        )
        d = r.json().get('data', {})
        return d.get('domain', '')
    except: return None


def buscar_email_completo(nombre, empresa, url='', ciudad='Colombia'):
    resultado = {
        'nombre': nombre,
        'empresa': empresa,
        'email': '',
        'email_verificado': False,
        'telefono': '',
        'linkedin': '',
        'fuentes_consultadas': [],
        'score_calidad': 0
    }

    # Extraer dominio de URL si existe
    dominio = ''
    if url:
        import re
        m = re.search(r'(?:https?://)?(?:www\.)?([^/]+)', url)
        if m:
            dominio = m.group(1)

    # Si no hay dominio, buscarlo con Hunter
    if not dominio and HUNTER_KEY:
        dominio = buscar_dominio_empresa(empresa) or ''

    # FUENTE 1: Apollo (emails + teléfonos)
    apollo = buscar_email_apollo(nombre, empresa, dominio)
    if apollo and apollo.get('email'):
        resultado['email'] = apollo['email']
        resultado['telefono'] = apollo.get('telefono', '')
        resultado['linkedin'] = apollo.get('linkedin', '')
        resultado['fuentes_consultadas'].append('apollo')
        resultado['score_calidad'] = 80

    # FUENTE 2: Hunter (verificar o encontrar)
    if resultado['email'] and HUNTER_KEY:
        verificacion = verificar_email_hunter(resultado['email'])
        if verificacion:
            resultado['email_verificado'] = verificacion.get('valido', False)
            resultado['score_calidad'] = verificacion.get('score', resultado['score_calidad'])
            resultado['fuentes_consultadas'].append('hunter_verify')
    elif dominio and HUNTER_KEY:
        hunter = buscar_email_hunter(nombre, dominio)
        if hunter and hunter.get('email'):
            resultado['email'] = hunter['email']
            resultado['email_verificado'] = hunter.get('score', 0) > 70
            resultado['fuentes_consultadas'].append('hunter')
            resultado['score_calidad'] = hunter.get('score', 0)

    # FUENTE 3: Skrapp (si no encontró email)
    if not resultado['email'] and SKRAPP_KEY:
        skrapp = buscar_email_skrapp(nombre, empresa)
        if skrapp and skrapp.get('email'):
            resultado['email'] = skrapp['email']
            resultado['fuentes_consultadas'].append('skrapp')
            resultado['score_calidad'] = 60

    # FUENTE 4: Snov (último recurso)
    if not resultado['email'] and dominio and SNOV_ID:
        snov = buscar_email_snov(nombre, dominio)
        if snov and snov.get('email'):
            resultado['email'] = snov['email']
            resultado['fuentes_consultadas'].append('snov')
            resultado['score_calidad'] = 55

    # Buscar teléfono WhatsApp si no tiene
    if not resultado['telefono'] and APOLLO_KEY:
        tel = buscar_telefono_whatsapp(nombre, empresa)
        if tel:
            resultado['telefono'] = tel.get('telefono', '')
            if 'apollo' not in resultado['fuentes_consultadas']:
                resultado['fuentes_consultadas'].append('apollo_tel')

    return resultado


if __name__ == '__main__':
    resultado = buscar_email_completo(
        nombre='Carlos Perez',
        empresa='Clinica Dental XYZ',
        url='https://clinicadental.com',
        ciudad='Medellin'
    )
    print('Email:', resultado['email'])
    print('Verificado:', resultado['email_verificado'])
    print('Telefono:', resultado['telefono'])
    print('Score:', resultado['score_calidad'])
    print('Fuentes:', resultado['fuentes_consultadas'])
