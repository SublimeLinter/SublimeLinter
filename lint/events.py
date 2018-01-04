from collections import defaultdict
import traceback


BEGIN_LINTING = 'BEGIN_LINTING'
FINISHED_LINTING = 'FINISHED_LINTING'


listeners = defaultdict(set)


def subscribe(topic, fn):
    listeners[topic].add(fn)


def unsubscribe(topic, fn):
    listeners[topic].remove(fn)


def broadcast(topic, message=None):
    payload = message.copy() or {}
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
