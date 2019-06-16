import difflib
import os

from argparse import ArgumentParser
from sys import argv
from sys import path

path.insert(0, '../')
from common.stanfordcorenlp.corenlpfactory import CoreNLPFactory
from common.triple import Triple

class RDFMaker:

    __predicates = {}
    __prefixed = {}
    __entities = {}

    __classes = {}
    __properties = {}
    __relations = set()

    def make(self, triples_filename, links_filename, verbose=False):
        if not triples_filename.startswith('/'):
            triples_filename = os.path.dirname(os.path.realpath(__file__)) + '/' + triples_filename

        if not links_filename.startswith('/'):
            links_filename = os.path.dirname(os.path.realpath(__file__)) + '/' + links_filename

        print('Processing predicates from {}'.format(triples_filename))

        self.__predicates = {}
        self.__prefixed = {'http://www.w3.org/2000/01/rdf-schema#': 'rdfs', 'http://local/local.owl#': 'local'}
        self.__entities = {}
        with open(links_filename, 'r') as links_file:
            for line in links_file.readlines():
                if len(line) < 2: continue

                if line.startswith('@PREFIX'):
                    line_list = line.split()
                    prefix = line_list[1]
                    prefix = prefix[:prefix.rfind(':')]

                    uri = line_list[2]
                    uri = uri[uri.find('<') + 1:uri.find('>')]

                    self.__prefixed.update({uri: prefix})

                elif line.startswith('@PREDICATE'):
                    line_list = line.split()
                    line = ' '.join(line_list[1:])

                    line_list = line.split(';')
                    predicate = line_list[0]
                    link = line_list[1]
                    self.__predicates.update({predicate: link})

                elif line.startswith('@ENTITY'):
                    line_list = line.split()
                    line = ' '.join(line_list[1:])

                    line_list = line.split(';')
                    entity = line_list[0]
                    links = line_list[1].split(',')
                    self.__entities.update({entity: links})

            links_file.close()

        with open(triples_filename, 'r') as triples_file:
            for line in triples_file.readlines():
                line_lst = line.replace('\"', '').split('\t')
                sentence_number = line_lst[0]
                subject = line_lst[1]
                predicate = line_lst[2]
                object = line_lst[3]

                triple = Triple(subject, predicate, object)

                predicate_link = self.__predicates[predicate]

                closest_subject = difflib.get_close_matches(subject, self.__entities)
                closest_object = difflib.get_close_matches(object, self.__entities)

                if len(closest_subject) < 1 or len(closest_object) < 1:
                    continue

                subject_link = self.__entities[closest_subject[0]]
                object_link = self.__entities[closest_object[0]]

                triple = Triple(closest_subject[0], predicate, closest_object[0])
                prefixes, classes, properties, relation = triple.get_turtle()
                self.__prefixed.update(prefixes)
                self.__classes.update(classes)
                self.__properties.update(properties)
                self.__relations.add(relation)
                
            triples_file.close()

        output_filename = os.path.splitext(triples_filename)[0] + '.ttl'
        open(output_filename, 'w').close() # Clean the file in case it exists

        with open(output_filename, 'a') as output_file:
            for key in self.__prefixed.keys():
                output_file.write('@prefix\t{}:\t<{}>\t.\n'.format(self.__prefixed[key], key))

            output_file.write('\n#### Classes ####\n\n')
            for key in self.__classes.keys():
                output_file.write('{}\n\n'.format(self.__classes[key]))

            output_file.write('#### Properties ####\n\n')
            for key in self.__properties.keys():
                output_file.write('{}\n\n'.format(self.__properties[key]))

            output_file.write('#### Relations ####\n\n')
            for relation in self.__relations:
                output_file.write('{}\n'.format(relation))

            output_file.close()
        print('Linked entities were stored at {}'.format(output_filename))

        return output_filename

    def __create_class(self, subject, predicate, object):
        name = subject.replace(' ', '_') + '_'
        uri = 'local:' + name

        content = uri + ' a rdfs:Class ;\n rdfs:label ' + entity + ' .\n'

        return content

def main(args):
    arg_p = ArgumentParser('python maker.py', description='Merges the unlinked triples with the corresponding entities and predicates.')
    arg_p.add_argument('-t', '--triples', type=str, default=None, help='Triples file')
    arg_p.add_argument('-l', '--links', type=str, default=None, help='Links file')
    arg_p.add_argument('-v', '--verbose', action='store_true', help='Prints extra information')

    args = arg_p.parse_args(args[1:])
    triples = args.triples
    links = args.links
    verbose = args.verbose

    if triples is None:
        print('No triples file provided.')
        exit(1)
    if links is None:
        print('No links file provided.')
        exit(1)

    maker = RDFMaker()
    maker.make(triples, links, verbose)

if __name__ == '__main__':
    exit(main(argv))
