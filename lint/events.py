from collections import defaultdict
import traceback


LINT_START = 'LINT_START'    # (buffer_id)
LINT_RESULT = 'LINT_RESULT'  # (filename, linter_name, errors)
LINT_END = 'LINT_END'        # (buffer_id)


listeners = defaultdict(set)


def subscribe(topic, fn):
    listeners[topic].add(fn)


def unsubscribe(topic, fn):
    try:
        listeners[topic].remove(fn)
    except KeyError:
        pass


def broadcast(topic, payload={}):
    for fn in listeners.get(topic, []):
        try:
            fn(**payload)
        except Exception:
            traceback.print_exc()


map_fn_to_topic = {}


def on(topic):
    def inner(fn):
        subscribe(topic, fn)
        map_fn_to_topic[fn] = topic
        return fn

    return inner


def off(fn):
    topic = map_fn_to_topic.get(fn, None)
    if topic:
        unsubscribe(topic, fn)
