import importlib, inspect
mod = importlib.import_module('google.generativeai')
print('module repr', mod)
print('version', getattr(mod,'__version__',None))
for name in dir(mod):
    if name.startswith('_'):
        continue
    obj = getattr(mod, name)
    if inspect.isfunction(obj) or inspect.isclass(obj):
        try:
            sig = inspect.signature(obj)
        except Exception:
            sig = '()'
        print(name, '->', sig)
