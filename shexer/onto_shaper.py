
from shexer.shaper import Shaper, TURTLE
from shexer.consts import JSON
from rdflib import Graph, RDF, URIRef, RDFS, OWL, XSD, Literal
from shexer.io.shape_map.shape_map_parser import _KEY_LABEL, _KEY_NODE_SELECTOR
from shexer.utils.uri import XSD_NAMESPACE

XSD_STRING = XSD.string
XSD_INTEGER = XSD.integer
XSD_DATE = XSD.date
XSD_BOOL = XSD.boolean
XSD_TIME = XSD.time
XSD_DECIMAL = XSD.decimal

import json


class OntoShaper(Shaper):
    def __init__(self, ontology_file,
                 base_ontology_name,
                 target_namespaces=None,
                 file_format=TURTLE,
                 extra_ontologies_dict=None,
                 namespaces_to_ignore=None,
                 depth=1):
        self._ontology_file = ontology_file
        self._target_namespaces = [] if target_namespaces is None else target_namespaces

        self._ontology_graph = self._build_rdflib_graph(file_format)
        self._kb = Graph()

        self._depth = depth
        self._namespaces_to_ignore = namespaces_to_ignore  # repeated in superclass, but I need it here

        self._external_ontologies_added = set()
        self._external_ontologies_added.add(base_ontology_name)
        self._extra_ontologies_dict = {} if extra_ontologies_dict is None else extra_ontologies_dict

        self._original_target_nodes = self._detect_target_nodes()  # List, rdflib_nodes
        # self._target_nodes = set()
        self._enrichment_dict = {}
        self._secondary_targets = set()
        self._fake_nodes_dict = {}  # class --> fake_node
        self._reversed_fake_nodes_dict = {}  # fake_node --> class

        self._fill_kb_with_initial_instances()
        self._decorate_graph()



        self._raw_shape_map = self._build_onto_shape_map()

        super().__init__(shape_map_raw=self._raw_shape_map,
                         raw_graph=self._serialize_graph(),
                         input_format=TURTLE,
                         shape_map_format=JSON,
                         namespaces_to_ignore=namespaces_to_ignore,
                         remove_empty_shapes=False,
                         depth_for_building_subgraph=depth)


    def _fill_kb_with_initial_instances(self):
        for a_target_class in self._original_target_nodes:
            self._add_fake_node_if_needed(a_target_class)


    def _add_fake_node_if_needed(self, target_type):
        """
        Create a fake node if needed, add it to internal dicts and to the kb graph
        :param target_type:
        :return:
        """

        if target_type in self._fake_nodes_dict:
            return
        if self._is_a_literal(target_type):
            self._add_fake_node_to_literal(target_type)
        else:
            self._add_fake_type_to_object(target_type)


    def _is_a_literal(self, target_type):
        if target_type == RDFS.Literal or target_type == RDF.langString or str(target_type).startswith(XSD_NAMESPACE):
            return True
        return False

    def _add_fake_type_to_object(self, target_type):
        fake_instance = URIRef(str(target_type+"_instance"))
        self._add_fake_node_to_dict(class_n=target_type, instance_n=fake_instance)
        self._kb.add((fake_instance, RDF.type, target_type))


    def _add_fake_node_to_literal(self, target_type):
        if target_type == XSD_STRING:
            fake = Literal("a", datatype=XSD_STRING)
        elif target_type == XSD_BOOL:
            fake = Literal("true", datatype=XSD_BOOL)
            # fake = '"true"^^<http://www.w3.org/2001/XMLSchema#boolean>'
        elif target_type == XSD_DATE:
            fake = Literal("1/10/1001", datatype=XSD_DATE)
            # fake = '"1/10/1001"^^<http://www.w3.org/2001/XMLSchema#date>'
        elif target_type == XSD_TIME:
            fake = Literal("21:32:52+02:00", datatype=XSD_TIME)
            # fake = '"21:32:52+02:00"^^<http://www.w3.org/2001/XMLSchema#time>'
        elif target_type == XSD_INTEGER:
            fake = Literal("1", datatype=XSD_INTEGER)
            # fake = '"1"^^<http://www.w3.org/2001/XMLSchema#integer>'
        elif target_type == XSD_DECIMAL:
            fake = Literal("1.1", datatype=XSD_DECIMAL)
            # fake = '"1.1"^^<http://www.w3.org/2001/XMLSchema#decimal>'
        elif target_type == RDFS.Literal:
            fake = Literal("A", datatype=RDFS.Literal)
            # fake = '"a"'
        elif target_type == RDF.langString:
            fake = Literal("A", lang="en")
            # fake = '"a"@en'
        else:
            raise ValueError("unknown literal type: " + str(target_type))
        self._add_fake_node_to_dict(class_n=target_type,
                                    instance_n=fake)

    def _decorate_graph(self):
        """
        Fill self._kb with all the triples needed

        :return:
        """
        self._decorate_target_nodes()
        self._decorate_secondary_targets()

    def _decorate_target_nodes(self):
        for a_target_node in self._original_target_nodes:
            # print("Winba!", a_target_node)
            self._enrichment_dict[a_target_node] = self._locate_classes(a_target_node)
        self._enrich_target_nodes(self._enrichment_dict)

    def _decorate_secondary_targets(self):
        if self._depth <= 1:
            return
        temporal_last_depth_explored = set()
        for elem in self._original_target_nodes:
            temporal_last_depth_explored.add(elem)

        self._decorate_secondary_layers(temporal_last_depth_explored)

        # while self._depth != 0 or len(temporal_last_depth_explored) != 0:
        #     nodes_decorated = self._decorate_secondary_layer(temporal_last_depth_explored)
        #     temporal_last_depth_explored.clear()
        #     for a_node in nodes_decorated:
        #         temporal_last_depth_explored.add(a_node)


    def _decorate_secondary_layers(self, seed_nodes):
        while self._depth > 1:
            self._depth -= 1
            types_to_decorate = self._get_secondary_types_of_seed_nodes(seed_nodes)
            enrich_dict = {}
            seed_nodes = set()  # Overwrite seed_nodes, already used to get the types to decorate
            for a_type in types_to_decorate:
                if a_type not in self._original_target_nodes:
                    self._secondary_targets.add(a_type)  # Update secondary_types set, to build an adequate shape_map
                seed_nodes.add(a_type)
                enrich_dict[a_type] = self._locate_classes(a_type)
            self._enrich_target_nodes(enrich_dict)


    def _get_secondary_types_of_seed_nodes(self, seed_nodes):
        result = set()
        for a_node in seed_nodes:
            for a_fake_node in self._get_secondary_fake_targets_of_a_node(a_node):
                result.add(self._class_of_fake_node(a_fake_node))
        return result

    def _get_secondary_fake_targets_of_a_node(self, target_node):
        result = set()
        for a_triple in self._ontology_graph.triples((URIRef(target_node), None, None)):
            if not isinstance(a_triple[2], Literal) and \
                    not self._belongs_to_excluded_namespace(a_triple[1]) and \
                    not a_triple[2] == OWL.Class:
                result.add(a_triple[2])
        return result


    def _enrich_target_nodes(self, enrichment_dict):
        """
        It receives a dict of rfdlib_node (class): {rdflib_classes} (every superclass), including the class itslef)

        :param enrichment_dict:
        :return:
        """
        for a_node, classes in enrichment_dict.items():
            # print("wiiii", a_node, classes)
            for a_class in classes:
                # rdflib_class = URIRef(a_class)
                # print("weeee", a_node, a_class)
                self._add_properties_of_class(a_node, a_class)
                # self._add_object_properties(rdflib_node, rdflib_class)
                # self._add_literal_properties(rdflib_node, rdflib_class)
                # self._add_general_properties(rdflib_node, rdflib_class)
                # for a_triple in self._ontology_graph.triples((rdflib_class, None, None)):
                #     self._ontology_graph.add((rdflib_node, a_triple[1], a_triple[2]))


    def _add_fake_node_to_dict(self, class_n, instance_n):
        self._fake_nodes_dict[class_n] = instance_n
        self._reversed_fake_nodes_dict[instance_n] = class_n

    def _fake_node_of_a_class(self, class_n):
        return self._fake_nodes_dict[class_n]

    def _class_of_fake_node(self, instance_n):
        # if instance_n in self._target_nodes:
        #     return instance_n
        # print(self._reversed_fake_nodes_dict)
        return self._reversed_fake_nodes_dict[instance_n]

    def _locate_classes(self, a_target_node):
        result = set()
        result.add(a_target_node)
        for a_triple in self._ontology_graph.triples((URIRef(a_target_node), RDFS.subClassOf, None)):
            result.add(a_triple[2])
            self._retrieve_ontology_if_needed(a_triple[2])
            for an_elem in self._locate_classes(a_triple[2]):
                result.add(an_elem)
        return result

    def _retrieve_ontology_if_needed(self, a_node):
        ontology_name = self._get_ontology_name_from_node(a_node)
        if ontology_name not in self._external_ontologies_added:
            self._external_ontologies_added.add(ontology_name)
            self._merge_ontology_in_graph(ontology_name)

    def _merge_ontology_in_graph(self, ontology_name):
        self._ontology_graph.parse(self._extra_ontologies_dict[ontology_name])

    def _add_properties_of_class(self, rdflib_onto_node, rdflib_class):
        for a_triple in self._ontology_graph.triples((None, RDFS.domain, rdflib_class)):
            target_property = a_triple[0]
            # print("WEEEE", rdflib_onto_node, rdflib_class)
            for a_triple in self._ontology_graph.triples((target_property, RDFS.range, None)):
                target_type = a_triple[2]
                self._add_enriched_triple(rdflib_onto_node, target_property, target_type)

    def _add_enriched_triple(self, rdflib_node, target_property, target_type):
        # print("Weeeee", rdflib_node, target_property, target_type)
        self._add_fake_node_if_needed(rdflib_node)
        self._add_fake_node_if_needed(target_type)
        self._kb.add((self._fake_node_of_a_class(rdflib_node), target_property, self._fake_node_of_a_class(target_type)))



    def _build_rdflib_graph(self, file_format):
        result = Graph()
        result.load(self._ontology_file, format=file_format)
        return result

    def _serialize_graph(self):
        # result = self._kb.serialize(format="turtle")
        # print(str(result).replace("\\n", "\n"))
        # return result
        return self._kb.serialize(format="turtle")


    def _belongs_to_excluded_namespace(self, rdflib_node):
        str_node = str(rdflib_node)
        for a_namespace in self._namespaces_to_ignore:
            if str_node.startswith(a_namespace):
                return True
        return False


    def _get_ontology_name_from_node(self, a_node):
        str_node = str(a_node)
        if "#" in str_node:
            return str_node[:str_node.rfind("#") + 1]
        else:
            return str_node[:str_node.rfind("/") + 1]

    def _build_onto_shape_map(self):
        json_map = [self._node_selector_for_a_node(a_node) for a_node in self._original_target_nodes] + \
                   [self._node_selector_for_a_node(a_node) for a_node in self._secondary_targets]
        # return json.dumps(json_map)
        result = json.dumps(json_map)
        print(result)
        return result


    def _node_selector_for_a_node(self, a_node):
        # print("Mhan llamau", a_node)
        return {_KEY_NODE_SELECTOR : "<" + a_node + "_instance>",
                _KEY_LABEL: "<" + self._shape_label_for_a_node(a_node) + ">"}

    def _shape_label_for_a_node(self, node_uri):
        # TODO WEah!! CHANGE THIS! this in soooo ad-hoc
        return node_uri.replace("asio/", "asio/shapes/")

    def _detect_target_nodes(self):
        candidate_nodes = []
        for a_triple in self._ontology_graph.triples((None, RDF.type, OWL.Class)):
            candidate_nodes.append(a_triple[0])
        return [a_node for a_node in candidate_nodes
                if self._belong_to_target_namespaces(str(a_node))]

    def _belong_to_target_namespaces(self, str_node):
        for a_target_namespace in self._target_namespaces:
            if str_node.startswith(a_target_namespace):
                return True
        return False
