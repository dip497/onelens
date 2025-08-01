import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { EpicStatus, EpicSummary } from '@/types';

interface EpicStatusChartProps {
  data: EpicSummary[];
}

const statusColors: Record<EpicStatus, string> = {
  [EpicStatus.DRAFT]: '#6b7280',
  [EpicStatus.ANALYSIS_PENDING]: '#eab308',
  [EpicStatus.ANALYZED]: '#3b82f6',
  [EpicStatus.APPROVED]: '#22c55e',
  [EpicStatus.IN_PROGRESS]: '#a855f7',
  [EpicStatus.DELIVERED]: '#10b981',
};

export function EpicStatusChart({ data }: EpicStatusChartProps) {
  const chartData = Object.values(EpicStatus).map((status) => {
    const item = data.find((d) => d.status === status);
    return {
      status: status.split(' ').map(word => word[0]).join(''), // Abbreviate status
      fullStatus: status,
      count: item?.count || 0,
      color: statusColors[status],
    };
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis 
          dataKey="status" 
          className="text-xs"
          tick={{ fill: 'currentColor' }}
        />
        <YAxis 
          className="text-xs"
          tick={{ fill: 'currentColor' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--background))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '6px',
          }}
          labelStyle={{ color: 'hsl(var(--foreground))' }}
          formatter={(value: any, name: any, props: any) => [
            value,
            props.payload.fullStatus,
          ]}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}