from shexer.shaper import Shaper
from rdflib import Graph, RDF, URIRef
from shexer.io.shape_map.shape_map_parser import _KEY_LABEL, _KEY_NODE_SELECTOR

import json

OWL_CLASS = URIRef("http://www.w3.org/2002/07/owl#class")

class OntoShaper(Shaper):
    def __init__(self, ontology_file, target_namespaces=None):
        self._ontology_file = ontology_file
        self._target_namespaces = [] if target_namespaces is None else target_namespaces

        self._graph = self._build_rdflib_graph()
        self._raw_shape_map = self._build_onto_shape_map()
        self._decorate_graph()

        super().__init__(shape_map_raw=self._raw_shape_map,
                         raw_graph=self._serialize_graph())


    def _build_rdflib_graph(self):
        result = Graph()
        result.load(self._ontology_file)
        return result


    def _build_onto_shape_map(self):
        target_nodes = self._detect_target_nodes()
        return self._build_shape_map_for_target_nodes(target_nodes)


    def _build_shape_map_for_target_nodes(self, target_nodes):
        json_map = [ self._node_selector_for_a_node(a_node) for a_node in target_nodes]
        return json.dumps(json_map)


    def _node_selector_for_a_node(self, a_node):
        return {_KEY_NODE_SELECTOR : a_node,
                _KEY_LABEL: self._shape_label_for_a_node(a_node)}


    def _shape_label_for_a_node(self, node_uri):
        # TODO WEah!! CHANGE THIS! this in soooo ad-hoc
        return node_uri.replace("asio/", "asio/shapes/")


    def _detect_target_nodes(self):
        candidate_nodes = []
        for a_triple in self._graph.triples((None, RDF.type, OWL_CLASS)):
            candidate_nodes.append(a_triple[0])
        return [a_node for a_node in candidate_nodes
                if self._belong_to_target_namespaces(str(a_node))]


    def _belong_to_target_namespaces(self, str_node):
        for a_target_namespace in self._target_namespaces:
            if str_node.startswith(a_target_namespace):
                return True
        return False