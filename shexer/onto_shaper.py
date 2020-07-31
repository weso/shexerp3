from shexer.shaper import Shaper, TURTLE
from rdflib import Graph, RDF, URIRef, RDFS
from shexer.io.shape_map.shape_map_parser import _KEY_LABEL, _KEY_NODE_SELECTOR

import json
import requests

OWL_CLASS = URIRef("http://www.w3.org/2002/07/owl#class")

class OntoShaper(Shaper):
    def __init__(self, ontology_file, target_namespaces=None):
        self._ontology_file = ontology_file
        self._target_namespaces = [] if target_namespaces is None else target_namespaces

        self._graph = self._build_rdflib_graph()

        self._external_ontologies_added = set()

        self._target_nodes = self._detect_target_nodes()
        self._raw_shape_map = self._build_onto_shape_map()
        self._decorate_graph()

        super().__init__(shape_map_raw=self._raw_shape_map,
                         raw_graph=self._serialize_graph(),
                         input_format=TURTLE)


    def _build_rdflib_graph(self):
        result = Graph()
        result.load(self._ontology_file)
        return result

    def _serialize_graph(self):
        return self._graph.serialize(format="turtle")

    def _decorate_graph(self):
        enrichment_dict = {}
        for a_target_node in self._target_nodes:
            enrichment_dict[a_target_node] = self._locate_external_classes(a_target_node)
        self._enrich_target_nodes(enrichment_dict)

    def _enrich_target_nodes(self, enrichment_dict):
        for a_node_key, extra_classes in enrichment_dict.items():
            rdflib_node = URIRef(a_node_key)
            for an_extra_class in extra_classes:
                rdflib_class = URIRef(an_extra_class)
                for a_triple in self._graph.triples((rdflib_class, None, None)):
                    self._graph.add((rdflib_node, a_triple[1], a_triple[2]))

    def _locate_external_classes(self, a_target_node):
        result = set()
        for a_triple in self._graph.triples((URIRef(a_target_node), RDFS.subClassOf, None)):
            result.add(str(a_triple[2]))
            self._retireve_ontology_if_needed(a_triple[2])
            for an_elem in self._locate_external_classes(a_triple[2]):
                result.add(an_elem)
        return result

    def _retireve_ontology_if_needed(self, a_node):
        ontology_name = self._get_ontology_name_from_node(a_node)
        if ontology_name not in self._external_ontologies_added:
            self._external_ontologies_added.add(ontology_name)
            self._merge_ontology_in_graph(ontology_name)

    def _merge_ontology_in_graph(self, ontology_name):
        str_ontology = self._download_ontology(ontology_name)
        self._graph.parse(data=str_ontology)

    def _download_ontology(self, ontology_name):
        res = requests.get(ontology_name, headers={"accept": "application/rdf+xml"})
        return res.text

    def _get_ontology_name_from_node(self, a_node):
        str_node = str(a_node)
        if "#" in str_node:
            return str_node[:str_node.rfind("#") + 1]
        else:
            return str_node[:str_node.rfind("/") + 1]

    def _build_onto_shape_map(self):
        return self._build_shape_map_for_target_nodes(self._target_nodes)

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
