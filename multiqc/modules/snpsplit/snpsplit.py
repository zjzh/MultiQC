#!/usr/bin/env python
"""MultiQC module to parse the output from SNPsplit"""
from collections import OrderedDict
import logging
import re

from multiqc import config
from multiqc.modules.base_module import BaseMultiqcModule
from multiqc.plots import bargraph

# Initialise the logger
log = logging.getLogger(__name__)

class MultiqcModule(BaseMultiqcModule):
    def __init__(self):
        super(MultiqcModule, self).__init__(
            name='SNPsplit',
            anchor='SNPsplit',
            target='SNPsplit',
            href='https://www.bioinformatics.babraham.ac.uk/projects/SNPsplit/',
            info='A tool to determine allele-specific alignments from high-throughput sequencing experiments that have been aligned to N-masked genomes'
        )

        # Parse reports
        self.snpsplit_data = dict()
        for f in self.find_log_files('SNPsplit'):
            parsed = self.parseSNPsplitOutput(f)
            if parsed:
                s_name = self.clean_s_name(parsed[0], f['root'])
                if s_name in self.snpsplit_data:
                    log.warning("Replacing duplicate sample {}".format(s_name))
                self.snpsplit_data[s_name] = parsed[1]
                self.add_data_source(f, s_name=s_name)

        if len(self.snpsplit_data) == 0:
            raise UserWarning
        log.info("Found {} reports".format(len(self.snpsplit_data)))

        self.allele_tagging_section()
        self.allele_sorting_section()

    def parseSNPsplitOutput(self, f):
        input_fn = None
        d = dict()

        for line in f['f'].splitlines():
            # Parse the sample name
            match = re.match(r"Input file:\W+'([^']+)'", line)
            if match:
                # Report can have two sections with two input files,
                # the second sorting the output from the tagging
                # Just take the first instance, which is the initial input file
                if input_fn is None:
                    input_fn = match.group(1)
                continue

            regex_patterns = [
                # Allele-tagging report
                ['tagging_skipped', r"Reads were unaligned and hence skipped: (\d+)"],
                ['tagging_unassignable', r"(\d+) reads were unassignable"],
                ['tagging_genome1', r"(\d+) reads were specific for genome 1"],
                ['tagging_genome2', r"(\d+) reads were specific for genome 2"],
                ['tagging_unassignableCT', r"(\d+) reads that were unassignable contained C>T SNPs"],
                ['tagging_ambiguous', r"(\d+) reads did not contain one of the expected bases"],
                ['tagging_conflictingSNPs', r"(\d+) contained conflicting allele-specific SNPs"],
                # Allele-specific sorting report
                ['sorting_conflictingReads', r"Reads contained conflicting SNP information:\W+(\d+)"]
            ]
            for (k, regex) in regex_patterns:
                match = re.match(regex, line)
                if match:
                    d[k] = int(match.group(1))
                    break

            # Allele-specific sorting report
            sorting_patterns = [
                ['sorting_unassignableReads', "Reads were unassignable"],
                ['sorting_unassignableReads', "Read pairs were unassignable (UA/UA):"],
                ['sorting_genome1Reads', "Reads were specific for genome 1"],
                ['sorting_genome1Reads', "Read pairs were specific for genome 1 (G1/G1)"],
                ['sorting_genome2Reads', "Reads were specific for genome 2"],
                ['sorting_genome2Reads', "Read pairs were specific for genome 2 (G2/G2)"],
                ['sorting_G1UA', "Read pairs were a mix of G1 and UA"],
                ['sorting_G2UA', "Read pairs were a mix of G2 and UA"],
                ['sorting_G1G2', "Read pairs were a mix of G1 and G2"],
                ['sorting_conflictingReads', "Read pairs contained conflicting SNP information"]
            ]
            for (k, pattern) in sorting_patterns:
                if line.startswith(pattern):
                    d[k] = int(line.split("\t")[-1].split()[0])
                    break

        return [input_fn, d]

    def allele_tagging_section(self):
        ''' Allele-tagging report '''
        cats = OrderedDict()
        cats['tagging_genome1'] = {'name':'Genome 1'}
        cats['tagging_genome2'] = {'name':'Genome 2'}
        cats['tagging_skipped'] = {'name':'Unaligned reads'}
        cats['tagging_unassignable'] = {'name':'Not assigned'}
        cats['tagging_ambiguous'] = {'name':'No match'}
        cats['tagging_conflictingSNPs'] = {'name':'Conflicting SNPs'}

        # Subtract ambiguous and C->T from unassignable
        CT = False
        for k, v in self.snpsplit_data.items():
            if 'tagging_unassignable' and 'tagging_ambiguous' in v:
                v['tagging_unassignable'] -= v['tagging_ambiguous']
            if 'tagging_unassignable' and 'tagging_unassignableCT' in v:
                v['tagging_unassignable'] -= v['tagging_unassignableCT']
                CT = True
        if CT:
            cats['tagging_unassignableCT'] = {'name': 'C->T SNP'}

        pconfig = {
            'id': 'snpsplit-allele-tagging-plot',
            'title': "SNPsplit: Allele-tagging report",
            'ylab': "Reads",
            'cpswitch_counts_label': 'Reads'
        }

        self.add_section(
            name="Allele-tagging report",
            description="Per-sample metrics of how many reads were assigned to each genome.",
            helptext="""
                Bar graph categories are:

                * `Genome 1`: Reads assigned to Genome 1
                * `Genome 2`: Reads assigned to Genome 2
                * `Unaligned reads`: Reads aren't aligned
                * `Not assigned`: Reads don't overlap a SNP
                * `No match`: Reads overlap informative SNPs, but don't contain the expected nucleotide for either genome
                * `Conflicting SNPs`: Reads overlapped multiple informative SNPs, but there was a conflict in support for assignment to one genome over the other between the SNPs
                * `C->T SNP`: (Bisulfite sequencing data only) Reads overlapping `C->T` SNPs may be unassigned
                """,
            plot=bargraph.plot(self.snpsplit_data, cats, pconfig)
        )

    def allele_sorting_section(self):
        ''' Allele-specific sorting report '''
        cats = OrderedDict()
        cats['sorting_genome1Reads'] = {'name': 'Genome 1'}
        cats['sorting_genome2Reads'] = {'name': 'Genome 2'}
        cats['sorting_unassignableReads'] = {'name': 'Not assigned'}
        cats['sorting_G1UA'] = {'name': 'Genome 1 / unassignable'}
        cats['sorting_G2UA'] = {'name': 'Genome 2 / unassignable'}
        cats['sorting_G1G2'] = {'name': 'Different genomes'}
        cats['sorting_conflictingReads'] = {'name': 'Conflicting SNPs'}

        pconfig = {
            'id': 'snpsplit-sorting-plot',
            'title': "SNPsplit: Allele-specific sorting",
            'ylab': "Reads",
            'cpswitch_counts_label': 'Reads'
        }

        self.add_section(
            name="Allele-specific sorting",
            description="Per-sample metrics of how reads and pairs of reads were sorted into each genome.",
            helptext="""
                Bargraph categories are:

                * `Genome 1`: Reads assigned to Genome 1
                * `Genome 2`: Reads assigned to Genome 2
                * `Not assigned`: Reads don't overlap a SNP
                * `Genome 1 / unassignable`: One paired-end read assigned to Genome 1, one unassignable (doesn't overlap a SNP)
                * `Genome 2 / unassignable`: One paired-end read assigned to Genome 2, one unassignable (doesn't overlap a SNP)
                * `Different genomes`: Paired-end reads assigned to different genomes
                * `Conflicting SNPs`: Reads overlapped multiple informative SNPs, but there was a conflict in support for assignment to one genome over the other between the SNPs

                Note that metrics here may differ from those in the allele-tagging report.
                This occurs when paired-end reads are used, since 'tagging' only one read in
                a pair as arising from one genome can suffice in both reads being sorted there.

                Similarly, if two reads in a pair are tagged as arising from different genomes
                then the pair becomes unassignable.
            """,
            plot=bargraph.plot(self.snpsplit_data, cats, pconfig)
        )
