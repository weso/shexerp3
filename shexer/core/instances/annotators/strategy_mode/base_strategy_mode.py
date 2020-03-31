class BaseStrategyMode(object):

    def __init__(self, anotator_ref):
        self._anotator_ref = anotator_ref
        self._instantiation_property = self._anotator_ref._instantiation_property
        self._instances_dict = self._anotator_ref._instances_dict
        self._instance_tracker = self._anotator_ref._instance_tracker

    def is_relevant_triple(self, a_triple):
        raise NotImplementedError()

    def annotate_triple(self, a_triple):
        raise NotImplementedError()
