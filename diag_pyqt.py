import sys, os, importlib.util
print('sys.version:', sys.version)
print('sys.executable:', sys.executable)
print('cwd:', os.getcwd())
print('PYTHONHOME:', os.environ.get('PYTHONHOME'))
print('PYTHONPATH:', os.environ.get('PYTHONPATH'))
print('\nsys.path:\n' + '\n'.join(sys.path))
print('\nFinding PyQt6 spec...')
spec = importlib.util.find_spec('PyQt6')
print('PyQt6 spec:', spec)
try:
    import PyQt6
    print('PyQt6 __file__:', getattr(PyQt6, '__file__', 'N/A'))
except Exception as e:
    print('import PyQt6 failed:', repr(e))

# Try to import QtCore specifically (this may raise the same ImportError)
print('\nTrying to import QtCore...')
try:
    from PyQt6 import QtCore
    print('QtCore imported, QT_VERSION_STR:', QtCore.QT_VERSION_STR)
except Exception as e:
    print('QtCore import failed:', repr(e))

# Locations to search for Qt6Core.dll
candidates = []
# site-packages locations
try:
    import site
    for p in site.getsitepackages():
        candidates.append(os.path.join(p, 'PyQt6', 'Qt6', 'bin'))
except Exception:
    pass
# user site-packages
try:
    import site
    user = site.getusersitepackages()
    candidates.append(os.path.join(user, 'PyQt6', 'Qt6', 'bin'))
except Exception:
    pass
# common Program Files folders
candidates += [r'C:\Program Files\Qt\bin', r'C:\Program Files\Qt', r'C:\Program Files (x86)\Qt']
# check dist internal
candidates.append(os.path.join(os.getcwd(), 'dist', 'desktop', '_internal'))

print('\nCandidates to check for Qt6Core.dll:')
for p in candidates:
    try:
        exists = os.path.exists(p)
    except Exception:
        exists = False
    print(p, 'exists=', exists)
    if exists:
        for root, dirs, files in os.walk(p):
            for f in files:
                if 'Qt6Core.dll' in f or 'Qt6' in f and f.endswith('.dll'):
                    print('  found:', os.path.join(root, f))

print('\nPATH entries containing Qt or PyQt6:')
for entry in os.environ.get('PATH','').split(os.pathsep):
    try:
        if 'Qt' in entry or 'PyQt' in entry:
            print('  ', entry)
    except Exception:
        pass

print('\nEND DIAG')
