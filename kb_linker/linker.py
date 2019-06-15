import os

from argparse import ArgumentParser
from nltk.tree import Tree
from sys import argv
from sys import path

path.insert(0, '../')
from common.babelfy.babelfywrapper import BabelfyWrapper
from common.ncbo.ncbowrapper import NCBOWrapper
from common.stanfordcorenlp.corenlpwrapper import CoreNLPWrapper
from common.utils import Utils

class Linker:

    def link(self, input_filename, k_base='babelfy', verbose=False):
        if not input_filename.startswith('/'):
            input_filename = os.path.dirname(os.path.realpath(__file__)) + '/' + input_filename

        print('Processing text from {}'.format(input_filename))

        with open(input_filename, 'r') as input_file:
            contents = input_file.read()
            input_file.close()

        linked = {}
        prefixed = {}
        k_bases = k_base.split(',')
        for base in k_bases:
            if base == 'babelfy':
                prefixes, links = self.__babelfy(contents, verbose)
                prefixed.update(prefixes)
                linked.update(links)
            elif base == 'ncbo':
                prefixes, links = self.__ncbo(contents, verbose)
                prefixed.update(prefixes)
                linked.update(links)
            else:
                raise Exception("Unknown knowledge base!")

        np_entities, verbs = self.__extract_np_and_verbs(contents)
        entities_linked = self.__associate_np_to_entities(np_entities, linked)
        verbs_linked = self.__associate_verbs_to_entities(verbs, linked)

        output_filename = os.path.splitext(input_filename)[0] + '_links.txt'
        open(output_filename, 'w').close() # Clean the file in case it exists

        with open(output_filename, 'a') as output_file:
            for key in prefixed.keys():
                output_file.write('@PREFIX\t{}:\t<{}>\n'.format(prefixed[key], key))

            for key in verbs_linked.keys():
                output_file.write('@PREDICATE\t{};{}\n'.format(key.encode('utf-8'), verbs_linked[key]))

            for key in entities_linked.keys():
                output_file.write('@ENTITY\t{};{}\n'.format(key.encode('utf-8'), entities_linked[key]))
            output_file.close()
        print('Linked entities were stored at {}'.format(output_filename))

        return output_filename

    def __babelfy(self, contents, verbose=False):
        if verbose:
            print('Searching for entities, concepts and their links, using the Babelfy base')

        babelfy = BabelfyWrapper()

        prefixes = {'http://babelnet.org/rdf/': 'bn'}
        links = {}
        annotated = babelfy.annotate(contents)

        for annotation in annotated:
            entity = BabelfyWrapper.frag(annotation, contents).upper()
            uri = annotation.babelnet_url()#annotation.babel_synset_id()#

            prefix = uri[:uri.rfind('/') + 1]
            suffix = uri[uri.rfind('/') + 1:]
            if not prefix in prefixes.keys():
                raise Exception('Unknown prefix: {}'.format(prefix))

            if verbose:
                print('Mapped "{}" to {}'.format(entity, uri))
                annotation.pprint()

            links[entity.lower()] = '{}:{}'.format(prefixes[prefix], suffix)

        return prefixes, links

    def __ncbo(self, contents, verbose=False):
        if verbose:
            print('Searching for entities, concepts and their links, using the NCBO base')

        ncbo = NCBOWrapper()
        annotated = ncbo.annotate(contents, ontologies='NCIT')

        prefixes = {'http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#': 'nci'}
        links = {}
        for annotation in annotated:
            annotated_class = annotation['annotatedClass']
            if not ('prefLabel' in annotated_class and '@id' in annotated_class):
                continue

            pref_label = annotated_class['prefLabel']
            uri = annotated_class['@id']
            ontology = annotated_class['links']['ontology']

            prefix = uri[:uri.rfind('#') + 1]
            suffix = uri[uri.rfind('#') + 1:]
            if not prefix in prefixes.keys():
                prefixes[prefix] = prefix[prefix.rfind('/') + 1:prefix.rfind('#')]

            try:
                pref_map_str = '{} \n--Ontology: {} \n--PrefLabel: {}'.format(uri, ontology, pref_label)
            except UnicodeEncodeError:
                continue # NCBO may present some Chinese characters. We will ignore them.

            for class_annotation in annotation['annotations']:
                entity = class_annotation['text']
                preferable_match = class_annotation['matchType'].upper() == 'PREF'

                if preferable_match or not entity in links:
                    if verbose:
                        print('-Mapped "{}" to {} \n--PrefMatch: {}'.format(entity, pref_map_str, preferable_match))

                    links[entity] = '{}:{}'.format(prefixes[prefix], suffix)
                    if preferable_match: break

        return prefixes, links

    def __extract_np_and_verbs(self, contents):
        print('Determining the noun-phrases (possible entities) and verbs (possible predicates). \n Please wait, as it may take a while ...')
        nlp = CoreNLPWrapper()
        annotated = nlp.annotate(contents, properties={'annotators': 'tokenize, ssplit, pos, lemma, ner, parse'})

        verb_set = set()
        entity_set = set()
        for sentence in annotated['sentences']:
            for token in sentence['tokens']:
                if token['pos'].startswith('VB'):
                    verb_set.add(token['word'])

            parsed_sentence = sentence['parse'].replace('\n', '')
            parse_tree = Tree.fromstring(parsed_sentence)
            for sub_tree in parse_tree.subtrees():
                if sub_tree.label() == 'NP':
                    np_entity = Utils.adjust_tokens(' '.join(sub_tree.leaves()), remove_punctuation=True)
                    if np_entity: # not empty
                        entity_set.add(np_entity)

        return entity_set, verb_set

    def __associate_np_to_entities(self, nps, links):
        nps_list = list(nps)
        nps_list.sort(key = len) # sort by string length

        np_entities = {}
        for np in nps_list:
            link_list = list()
            for key in links:
                if key.lower() == np.lower(): # exact match
                    link_list = [links[key]]
                    break;
                elif key.lower() in np.lower(): # composite
                    link_list.append(links[key])

            if not len(link_list) == 0:
                np_entities[np.lower()] = ','.join(link_list)

        for np in nps_list:
            if not np.lower() in np_entities.keys():
                np_entities[np.lower()] = 'notfound:' + np.lower().replace(' ', '_')

        return np_entities

    def __associate_verbs_to_entities(self, verbs, links):
        verbs_list = list(verbs)

        verbs_entities = {}
        for verb in verbs_list:
            for key in links:
                if verb.lower() in key.lower():
                    verbs_entities[verb.lower()] = links[key]
                    break

        for verb in verbs_list:
            if not verb.lower() in verbs_entities.keys():
                verbs_entities[verb.lower()] = 'notfound:' + verb.lower()

        return verbs_entities

def main(args):
    arg_p = ArgumentParser('python linker.py', description='Links the text entities to URIs from a knowledge base.')
    arg_p.add_argument('-f', '--filename', type=str, default=None, help='Text file')
    arg_p.add_argument('-k', '--kgbase', type=str, default='babelfy', help='Knowledge base to be used, e.g. babelfy (default) or ncbo')
    arg_p.add_argument('-v', '--verbose', action='store_true', help='Prints extra information')

    args = arg_p.parse_args(args[1:])
    filename = args.filename
    kg_base = args.kgbase
    verbose = args.verbose

    if filename is None:
        print('No file provided.')
        exit(1)

    linker = Linker()
    linker.link(filename, kg_base, verbose)

if __name__ == '__main__':
    exit(main(argv))