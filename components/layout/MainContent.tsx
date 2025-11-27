import React from 'react';
import { AgCard, AgButton, AgBadge } from '../ui/AgComponents';
import { BarChart3, Table, Image as ImageIcon, FileText, Download, MoreHorizontal, Share2, Database, ExternalLink } from 'lucide-react';

export const MainContent: React.FC = () => {
  return (
    <div className="flex-1 h-full bg-neutral-50/50 dark:bg-neutral-950 overflow-y-auto p-4 md:p-8 scroll-smooth border-r border-neutral-200 dark:border-neutral-800">
      <div className="max-w-5xl mx-auto space-y-8">
        
        {/* Header Section */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold text-neutral-900 dark:text-white mb-2">Project Workspace</h1>
            <p className="text-neutral-500 dark:text-neutral-400 text-sm md:text-base">Generated artifacts and retrieved documents appear here.</p>
          </div>
          <div className="flex gap-2">
            <AgButton variant="secondary" size="sm" className="hidden md:flex gap-2">
              <Share2 size={16} />
              Share
            </AgButton>
            <AgButton variant="icon" size="sm">
              <MoreHorizontal size={20} />
            </AgButton>
          </div>
        </div>

        {/* Mock Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
           <AgCard className="p-4 hover:shadow-md transition-all duration-200 cursor-pointer group border-neutral-200/60 dark:border-neutral-800">
             <div className="flex justify-between items-start mb-3">
               <div className="h-10 w-10 bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg flex items-center justify-center group-hover:bg-blue-100 dark:group-hover:bg-blue-900/50 transition-colors">
                 <BarChart3 size={20} />
               </div>
               <span className="text-[10px] bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 px-2 py-0.5 rounded-full">v1.2</span>
             </div>
             <h3 className="font-medium text-neutral-900 dark:text-white">Q3 Performance</h3>
             <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 line-clamp-2">Quarterly analysis of user acquisition and retention metrics.</p>
           </AgCard>
           
           <AgCard className="p-4 hover:shadow-md transition-all duration-200 cursor-pointer group border-neutral-200/60 dark:border-neutral-800">
             <div className="flex justify-between items-start mb-3">
               <div className="h-10 w-10 bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 rounded-lg flex items-center justify-center group-hover:bg-purple-100 dark:group-hover:bg-purple-900/50 transition-colors">
                 <Table size={20} />
               </div>
               <span className="text-[10px] bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 px-2 py-0.5 rounded-full">CSV</span>
             </div>
             <h3 className="font-medium text-neutral-900 dark:text-white">User Data Export</h3>
             <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 line-clamp-2">Cleaned dataset of active users from the last 30 days.</p>
           </AgCard>

           <AgCard className="p-4 hover:shadow-md transition-all duration-200 cursor-pointer group border-neutral-200/60 dark:border-neutral-800">
             <div className="flex justify-between items-start mb-3">
               <div className="h-10 w-10 bg-orange-50 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 rounded-lg flex items-center justify-center group-hover:bg-orange-100 dark:group-hover:bg-orange-900/50 transition-colors">
                 <ImageIcon size={20} />
               </div>
               <span className="text-[10px] bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 px-2 py-0.5 rounded-full">4 files</span>
             </div>
             <h3 className="font-medium text-neutral-900 dark:text-white">Hero Assets</h3>
             <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 line-clamp-2">Generated variations for the landing page hero section.</p>
           </AgCard>
        </div>

        {/* Active Document */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-white uppercase tracking-wider">Active Document</h2>
          </div>
          
          <AgCard className="overflow-hidden bg-white dark:bg-neutral-900 shadow-sm ring-1 ring-black/5 dark:ring-white/5">
            <div className="border-b border-neutral-100 dark:border-neutral-800 bg-neutral-50/30 dark:bg-neutral-900/30 px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-brand-600 dark:text-brand-400" />
                <span className="text-sm font-medium text-neutral-700 dark:text-neutral-200">analysis_report_v2.md</span>
              </div>
              <div className="flex gap-2">
                 <AgButton variant="ghost" size="sm" className="h-8 w-8 p-0">
                  <Download size={16} />
                 </AgButton>
                 <AgButton variant="secondary" size="sm" className="text-xs h-8">Edit</AgButton>
              </div>
            </div>
            
            <div className="p-6 md:p-10 bg-white dark:bg-neutral-900 min-h-[500px] text-sm md:text-base">
               {/* Mock Content Content */}
               <div className="prose prose-neutral dark:prose-invert prose-sm md:prose-base max-w-none">
                  <h2 className="text-xl font-bold text-neutral-900 dark:text-white mb-4">Executive Summary</h2>
                  <p className="text-neutral-600 dark:text-neutral-300 mb-6 leading-relaxed">
                    The Q3 financial results indicate a strong upward trend in user acquisition costs (CAC) offset by a 
                    significant increase in lifetime value (LTV). Initial projections suggest a 15% margin improvement 
                    if current retention strategies are maintained.
                  </p>
                  
                  <h3 className="text-lg font-semibold text-neutral-800 dark:text-neutral-200 mb-3">Key Metrics Breakdown</h3>
                  <div className="my-6 border border-neutral-200 dark:border-neutral-800 rounded-lg overflow-hidden shadow-sm">
                    <table className="w-full text-sm text-left">
                      <thead className="bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 font-medium border-b border-neutral-200 dark:border-neutral-800">
                        <tr>
                          <th className="px-4 py-3">Metric</th>
                          <th className="px-4 py-3">Q2 2024</th>
                          <th className="px-4 py-3">Q3 2024</th>
                          <th className="px-4 py-3 text-right">Delta</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800 bg-white dark:bg-neutral-900">
                        <tr className="hover:bg-neutral-50/50 dark:hover:bg-neutral-800/50">
                          <td className="px-4 py-3 font-medium text-neutral-900 dark:text-neutral-100">Revenue</td>
                          <td className="px-4 py-3 text-neutral-600 dark:text-neutral-400">$1.2M</td>
                          <td className="px-4 py-3 text-neutral-600 dark:text-neutral-400">$1.45M</td>
                          <td className="px-4 py-3 text-right text-emerald-600 dark:text-emerald-500 font-medium">+20.8%</td>
                        </tr>
                        <tr className="hover:bg-neutral-50/50 dark:hover:bg-neutral-800/50">
                          <td className="px-4 py-3 font-medium text-neutral-900 dark:text-neutral-100">Users</td>
                          <td className="px-4 py-3 text-neutral-600 dark:text-neutral-400">45k</td>
                          <td className="px-4 py-3 text-neutral-600 dark:text-neutral-400">52k</td>
                          <td className="px-4 py-3 text-right text-emerald-600 dark:text-emerald-500 font-medium">+15.5%</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <p className="text-neutral-600 dark:text-neutral-300 leading-relaxed mb-4">
                    Moving forward, resources should be reallocated towards the high-performing cohorts identified in the 
                    secondary analysis. This shift aligns with the broader strategic goals outlined in the annual roadmap.
                  </p>
               </div>
            </div>
          </AgCard>
        </div>

        {/* Retrieved Context Chunks */}
        <div className="space-y-3 pt-4 border-t border-neutral-200 dark:border-neutral-800">
           <div className="flex items-center gap-2 mb-2">
              <div className="h-6 w-6 rounded bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
                 <Database size={14} />
              </div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-white uppercase tracking-wider">Retrieved Context</h2>
              <span className="text-xs text-neutral-400 dark:text-neutral-500 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded-full">RAG Pipeline</span>
           </div>

           <div className="grid grid-cols-1 gap-3">
              <AgCard className="p-4 bg-slate-50 dark:bg-neutral-800 border-indigo-100/50 dark:border-indigo-900/30 hover:border-indigo-200 dark:hover:border-indigo-800 transition-colors">
                 <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                       <AgBadge variant="default">Score: 0.92</AgBadge>
                       <span className="text-xs font-mono text-neutral-500 dark:text-neutral-400">doc_finance_q3.pdf</span>
                    </div>
                    <ExternalLink size={14} className="text-neutral-400 hover:text-indigo-600 dark:hover:text-indigo-400 cursor-pointer" />
                 </div>
                 <p className="text-xs text-neutral-600 dark:text-neutral-300 font-mono leading-relaxed bg-white dark:bg-neutral-900 p-2 rounded border border-neutral-100 dark:border-neutral-700">
                    ...operating margin increased by 15% due to improved LTV/CAC ratios in the North American sector. 
                    Retention analysis suggests a 40% improvement in cohort stickiness...
                 </p>
              </AgCard>

              <AgCard className="p-4 bg-slate-50 dark:bg-neutral-800 border-indigo-100/50 dark:border-indigo-900/30 hover:border-indigo-200 dark:hover:border-indigo-800 transition-colors">
                 <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                       <AgBadge variant="default">Score: 0.88</AgBadge>
                       <span className="text-xs font-mono text-neutral-500 dark:text-neutral-400">meeting_notes_sept.txt</span>
                    </div>
                    <ExternalLink size={14} className="text-neutral-400 hover:text-indigo-600 dark:hover:text-indigo-400 cursor-pointer" />
                 </div>
                 <p className="text-xs text-neutral-600 dark:text-neutral-300 font-mono leading-relaxed bg-white dark:bg-neutral-900 p-2 rounded border border-neutral-100 dark:border-neutral-700">
                    Action item: Reallocate marketing spend to high-performing channels identified in Q2. 
                    Team agreed to focus on organic growth levers...
                 </p>
              </AgCard>
           </div>
        </div>

      </div>
    </div>
  );
};