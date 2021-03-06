# -*- coding: utf-8 -*-
#
# Copyright 2014 Institut für Experimentelle Kernphysik - Karlsruher Institut für Technologie
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import hf
import time
import os
import numpy as np
from sqlalchemy import *
import json

class XRootD(hf.module.ModuleBase):
    config_keys = {
        'source_url': ('Source File', ''),
        'tier_name': ('Tier to be monitored', '')
    }
    config_hint = ''

    table_columns = [Column('tier_name', TEXT),
                     Column('filename_plot', TEXT),
                     Column('attribute', TEXT)
                     ], ['filename_plot']

    subtable_columns = {
        'details': ([
            Column("date", TEXT),
            Column("plot_data", FLOAT), # used for rate
            Column("plot_data_active", FLOAT),
            Column("plot_data_finished", FLOAT)
        ], [])
    }

    def prepareAcquisition(self):
        self.source = hf.downloadService.addDownload(self.config['source_url'])
        self.source_url = self.source.getSourceUrl()
        self.details_list = []

    def extractData(self):
        #Imports for matplotlib & scipy must be made here, otherwise the module wouldn't be threadsafe.
        #This would lead to server problems.
        import matplotlib
        import matplotlib.pyplot as plt
        from scipy.interpolate import spline
        
        data = {}
        list_of_details = []
        plot_date = []
        plot_attribute = []
        with open(self.source.getTmpPath(), 'r') as f:
            data_object = json.loads(f.read())

        for group in data_object['transfers']:
            if str(group['name']) == self.config['tier_name']:
                for jobs in group['bins']:
                    details = {}
                    struct_time = time.strptime(jobs['start_time'], "%Y-%m-%dT%H:%M:%S")
                    details['date'] = time.strftime("%Y-%m-%d %H:%M", struct_time)
                    details['plot_data'] = (float(jobs['finished'])/float(jobs['active'])*
                                           float(jobs['bytes'])/float(jobs['active_time'])/
                                           1000000.0)
                    details['plot_data_active'] = float(jobs['active'])
                    details['plot_data_finished'] = float(jobs['finished'])
                    list_of_details.append(details)
                break
        data['attribute'] = "all information"

        list_of_details = sorted(list_of_details, key = lambda k: k['date'])
        self.details_list = list_of_details
        data['tier_name'] = self.config['tier_name']
              
        ######################################
        ####PLOT#####################
        
        #Plot-lists
        datetime_list = []
        rate_list = []
        finished_list = []
        running_list = []

        for job in list_of_details:
            rate_list.append(job['plot_data'])
            finished_list.append(job['plot_data_finished'])
            running_list.append(job['plot_data_active'] - job['plot_data_finished'])
            datetime_list.append(job['date'])
        
        fig, ax1 = plt.subplots()
        index_list = np.arange(len(rate_list))
        ax1.set_title(self.config['tier_name'])
        ax1.set_xticks(index_list+0.5)
        ax1.set_xticklabels(datetime_list, rotation='vertical')
        pos1_old = ax1.get_position()
        ax1.set_position([pos1_old.x0,pos1_old.y0+0.2,pos1_old.width,pos1_old.height-0.2])
        ax2 = ax1.twinx()
        pos2_old = ax2.get_position()
        ax2.set_position([pos2_old.x0,pos2_old.y0+0.2,pos2_old.width,pos2_old.height-0.2])

        ax1.bar(index_list, finished_list, 1.0, color='mediumslateblue', label='finished')
        ax1.bar(index_list, running_list, 1.0, color='cornflowerblue',bottom=finished_list, label='running')
        ax1.set_ylabel('active = finished + running transfers', color='darkslateblue')
        y1_min, y1_max = ax1.get_ylim()
        ax1.set_ylim(0., y1_max*1.25) #Try to avoid histogram overlapping with legend.
        for tl in ax1.get_yticklabels():
            tl.set_color('darkslateblue')
        # Legend for histograms only when data available
        if len(datetime_list) > 0:
            ax1.legend(loc='upper left')
        else:
            ax1.set_xlabel('NO DATA AVAILABLE')
        
        # Only interpolate when enough datapoints there
        if len(datetime_list) > 2:
            smooth_index_list = np.linspace(index_list.min(),index_list.max(),300)
            smooth_rate_list = spline(index_list,rate_list,smooth_index_list)
            
            #Sorting out negative rate values due to bad interpolation
            smooth_rate_list = [x if x >= 0. else 0. for x in smooth_rate_list]
            
            ax2.plot(smooth_index_list+0.5, smooth_rate_list, 'r-',label="interpolated rate")
            ax2.legend(loc='upper right')
        else:
            ax2.plot(index_list+0.5,rate_list, 'r-')
        
        y2_min, y2_max = ax2.get_ylim()
        ax2.set_ylim(0., y2_max*1.25) #Try to avoid curve overlapping with legend.
        for tl in ax2.get_yticklabels():
            tl.set_color('r')
        ax2.set_ylabel('Average transfer rate per file (MB/s)', color='r')
        fig.savefig(hf.downloadService.getArchivePath(
            self.run, self.instance_name + '_xrootd.png'), dpi=60)
        data['filename_plot'] = self.instance_name + '_xrootd.png'
        
        return data
        
    def fillSubtables(self, parent_id):
        self.subtables['details'].insert().execute(
            [dict(parent_id=parent_id, **row) for row in self.details_list])

    def getTemplateData(self):
        data = hf.module.ModuleBase.getTemplateData(self)
        
        details_list = self.subtables['details'].select().where(
            self.subtables['details'].c.parent_id==self.dataset['id']
            ).execute().fetchall()
        details_list = map(lambda x: dict(x), details_list)
        
        data['details'] = sorted(details_list, key = lambda k: k['date'])
        return data

