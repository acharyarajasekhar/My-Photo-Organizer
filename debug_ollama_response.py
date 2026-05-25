import json
import pprint

try:
    import ollama
    from ollama import Client
except Exception as e:
    print('ollama import error:', e)
    raise

client = Client()
imgs = ['test_photos/event1_1.jpg', 'test_photos/event1_2.jpg', 'test_photos/event1_3.jpg']
prompt = (
    "These images were taken at the same event. Provide a concise 2-4 word "
    "title suitable as a folder name for these photos. Respond ONLY with the title."
)

print('Calling ollama.generate...')
resp = client.generate(model='llava', prompt=prompt, images=imgs, stream=False)
print('type(resp)=', type(resp))
print('\nrepr(resp)=')
print(repr(resp))
print('\nresp (pprint)=')
try:
    pprint.pprint(resp)
except Exception:
    print('Could not pprint resp')

# Try to inspect attributes
print('\nattrs:')
for attr in dir(resp):
    if not attr.startswith('_'):
        try:
            val = getattr(resp, attr)
            print(attr, '=>', type(val))
        except Exception:
            pass

# If resp is dict-like, dump as json
try:
    print('\nJSON dump:')
    print(json.dumps(resp, default=str, indent=2))
except Exception:
    print('Not JSON serializable')

print('\nDone')
