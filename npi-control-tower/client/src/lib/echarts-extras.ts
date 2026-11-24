/**
 * AppKit's charts register a minimal ECharts build. The launch ramp chart also uses mark lines (SOP) and
 * mark areas (shortfall weeks), so register those two components on the same ECharts core instance.
 */
import * as echarts from 'echarts/core';
import { MarkAreaComponent, MarkLineComponent } from 'echarts/components';

echarts.use([MarkAreaComponent, MarkLineComponent]);
