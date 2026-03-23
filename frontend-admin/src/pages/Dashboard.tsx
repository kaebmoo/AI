import React from 'react'
import {
    Alert,
    Button,
    Card,
    Col,
    Empty,
    Progress,
    Row,
    Space,
    Spin,
    Statistic,
    Tag,
    Typography,
    message,
} from 'antd'
import {
    ClockCircleOutlined,
    CloudOutlined,
    DatabaseOutlined,
    FileSearchOutlined,
    FireOutlined,
    MessageOutlined,
    ReloadOutlined,
    SafetyCertificateOutlined,
    SyncOutlined,
    ThunderboltOutlined,
    WarningOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { adminService } from '../services/adminService'

const { Title, Paragraph, Text } = Typography;

const stackRowStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '8px 0',
    borderBottom: '1px solid #f0f0f0',
};

const textStackStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    minWidth: 0,
};

const Dashboard: React.FC = () => {
    const navigate = useNavigate();
    const queryClient = useQueryClient();

    const { data, isLoading, error } = useQuery({
        queryKey: ['dashboard_overview'],
        queryFn: () => adminService.getDashboardOverview()
    });

    const refreshMetadataMutation = useMutation({
        mutationFn: () => adminService.refreshCache(),
        onSuccess: async () => {
            message.success('Schema cache refreshed');
            await queryClient.invalidateQueries({ queryKey: ['dashboard_overview'] });
        },
        onError: (mutationError: Error) => {
            message.error(mutationError.message || 'Failed to refresh schema cache');
        }
    });

    const syncBrainMutation = useMutation({
        mutationFn: () => adminService.syncBrain(),
        onSuccess: async () => {
            message.success('Vanna brain synced');
            await queryClient.invalidateQueries({ queryKey: ['dashboard_overview'] });
        },
        onError: (mutationError: Error) => {
            message.error(mutationError.message || 'Failed to sync Vanna brain');
        }
    });

    const clearQueryCacheMutation = useMutation({
        mutationFn: () => adminService.clearQueryCache(),
        onSuccess: async () => {
            message.success('Query cache cleared');
            await queryClient.invalidateQueries({ queryKey: ['dashboard_overview'] });
        },
        onError: (mutationError: Error) => {
            message.error(mutationError.message || 'Failed to clear query cache');
        }
    });

    const formatTimestamp = (value?: string | null) => {
        if (!value) {
            return 'Never';
        }

        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }

        return parsed.toLocaleString();
    };

    if (isLoading) {
        return <div style={{ textAlign: 'center', marginTop: 50 }}><Spin size="large" /></div>;
    }

    if (error) {
        return <Alert message="Error loading dashboard overview" type="error" />;
    }

    if (!data) {
        return <Empty description="No dashboard data available" />;
    }

    const activeFeatureTags = data.effective_ai.enabled_features.slice(0, 6);

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap' }}>
                <div style={{ maxWidth: 720 }}>
                    <Title level={2} style={{ margin: 0 }}>Admin Overview</Title>
                    <Paragraph style={{ margin: '8px 0 0', color: '#4b5563' }}>
                        Operate the AI stack, monitor query quality, and track data-admin coverage from one view. Values here are pulled from the same runtime config and analytics APIs used elsewhere in admin.
                    </Paragraph>
                    <Space size={8} wrap>
                        <Tag color={data.effective_ai.fallback_in_use ? 'orange' : 'green'}>
                            {data.effective_ai.fallback_in_use ? 'Fallback config in use' : 'DB-backed runtime config'}
                        </Tag>
                        <Tag color={data.effective_ai.provider_alignment && data.effective_ai.model_alignment ? 'green' : 'red'}>
                            {data.effective_ai.provider_alignment && data.effective_ai.model_alignment ? 'Config aligned' : 'Config mismatch detected'}
                        </Tag>
                        <Tag color="blue">Updated {formatTimestamp(data.generated_at)}</Tag>
                    </Space>
                </div>

                <Space wrap>
                    <Button icon={<ReloadOutlined />} onClick={() => queryClient.invalidateQueries({ queryKey: ['dashboard_overview'] })}>
                        Refresh View
                    </Button>
                    <Button icon={<DatabaseOutlined />} loading={refreshMetadataMutation.isPending} onClick={() => refreshMetadataMutation.mutate()}>
                        Refresh Schema Cache
                    </Button>
                    <Button icon={<SyncOutlined />} loading={syncBrainMutation.isPending} onClick={() => syncBrainMutation.mutate()}>
                        Sync Vanna Brain
                    </Button>
                    <Button icon={<ThunderboltOutlined />} loading={clearQueryCacheMutation.isPending} onClick={() => clearQueryCacheMutation.mutate()}>
                        Clear Query Cache
                    </Button>
                </Space>
            </div>

            <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
                <Col xs={24} md={12} xl={6}>
                    <Card>
                        <Statistic
                            title="Default AI Runtime"
                            value={data.effective_ai.default_provider.display_name}
                            prefix={<CloudOutlined />}
                        />
                        <Text type="secondary">{data.effective_ai.default_model.display_name || 'No default model'}</Text>
                    </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                    <Card>
                        <Statistic
                            title="Queries (7 days)"
                            value={data.usage.total_queries_7d}
                            prefix={<FileSearchOutlined />}
                        />
                        <Text type="secondary">Avg {data.usage.avg_execution_time_ms_7d.toFixed(1)} ms</Text>
                    </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                    <Card>
                        <Statistic
                            title="Satisfaction (30 days)"
                            value={data.feedback.satisfaction_rate_30d}
                            suffix="%"
                            precision={1}
                            prefix={<MessageOutlined />}
                        />
                        <Text type="secondary">{data.feedback.total_feedback_30d} feedback items</Text>
                    </Card>
                </Col>
                <Col xs={24} md={12} xl={6}>
                    <Card>
                        <Statistic
                            title="Pending Reviews"
                            value={data.feedback.pending_reviews}
                            prefix={<SafetyCertificateOutlined />}
                        />
                        <Text type="secondary">{data.data_admin.active_warnings} active warning rules</Text>
                    </Card>
                </Col>
            </Row>

            <Row gutter={[16, 16]}>
                <Col xs={24} xl={14}>
                    <Card title="System Health" extra={<Button type="link" onClick={() => navigate('/models')}>Open models</Button>} style={{ marginBottom: 16 }}>
                        <Row gutter={[16, 16]}>
                            <Col xs={24} md={12}>
                                <Text type="secondary">Effective provider</Text>
                                <Title level={4} style={{ marginTop: 4, marginBottom: 4 }}>{data.effective_ai.default_provider.display_name}</Title>
                                <Text>{data.effective_ai.default_model.display_name || 'No default model configured'}</Text>
                                <div style={{ marginTop: 12 }}>
                                    <Tag color={data.effective_ai.default_provider.is_active ? 'green' : 'red'}>
                                        {data.effective_ai.default_provider.is_active ? 'Provider active' : 'Provider inactive'}
                                    </Tag>
                                    <Tag color={data.effective_ai.default_model.is_active ? 'green' : 'orange'}>
                                        {data.effective_ai.default_model.is_active ? 'Model active' : 'Model inactive'}
                                    </Tag>
                                </div>
                            </Col>
                            <Col xs={24} md={12}>
                                <div>
                                    {[
                                        `Providers: ${data.effective_ai.active_provider_count} active / ${data.effective_ai.total_provider_count} total`,
                                        `Models: ${data.effective_ai.active_model_count} active / ${data.effective_ai.total_model_count} total`,
                                        `Last brain sync: ${formatTimestamp(data.effective_ai.last_brain_sync_at)}`,
                                        `Feature flags enabled: ${data.effective_ai.enabled_features.length}`,
                                    ].map((item) => (
                                        <div key={item} style={stackRowStyle}>
                                            <Text>{item}</Text>
                                        </div>
                                    ))}
                                </div>
                            </Col>
                        </Row>

                        <div style={{ marginTop: 16 }}>
                            <Text type="secondary">Active providers</Text>
                            <div style={{ marginTop: 8 }}>
                                <Space wrap>
                                    {data.effective_ai.active_providers.map((provider) => (
                                        <Tag key={provider.id} color={provider.is_default ? 'blue' : 'default'}>
                                            {provider.display_name} · {provider.model}
                                        </Tag>
                                    ))}
                                </Space>
                            </div>
                        </div>

                        <div style={{ marginTop: 16 }}>
                            <Text type="secondary">Enabled features</Text>
                            <div style={{ marginTop: 8 }}>
                                <Space wrap>
                                    {activeFeatureTags.length > 0 ? activeFeatureTags.map((feature) => (
                                        <Tag key={feature}>{feature}</Tag>
                                    )) : <Text type="secondary">No features enabled</Text>}
                                </Space>
                            </div>
                        </div>
                    </Card>

                    <Card title="Usage and Quality" extra={<Button type="link" onClick={() => navigate('/query-logs')}>Open query logs</Button>}>
                        <Row gutter={[16, 16]}>
                            <Col xs={24} md={10}>
                                <div style={{ marginBottom: 16 }}>
                                    <Text type="secondary">Error rate (7 days)</Text>
                                    <Progress
                                        percent={Number((data.usage.error_rate_7d * 100).toFixed(1))}
                                        status={data.usage.error_rate_7d >= 0.1 ? 'exception' : 'active'}
                                    />
                                </div>
                                <div>
                                    {[
                                        `Failed queries: ${data.usage.error_count_7d}`,
                                        `Average execution time: ${data.usage.avg_execution_time_ms_7d.toFixed(1)} ms`,
                                        `Average tokens used: ${data.usage.avg_tokens_used_7d.toLocaleString()}`,
                                        `Thumbs down (30 days): ${data.feedback.thumbs_down_30d}`,
                                    ].map((item) => (
                                        <div key={item} style={stackRowStyle}>
                                            <Text>{item}</Text>
                                        </div>
                                    ))}
                                </div>
                            </Col>
                            <Col xs={24} md={14}>
                                <Text type="secondary">Top contexts in the last 7 days</Text>
                                <div style={{ marginTop: 8 }}>
                                    {data.usage.top_contexts_7d.length > 0 ? data.usage.top_contexts_7d.map((item) => (
                                        <div key={item.context_name} style={stackRowStyle}>
                                            <Text>{item.context_name}</Text>
                                            <Tag color="blue">{item.count}</Tag>
                                        </div>
                                    )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No recent query traffic" />}
                                </div>
                            </Col>
                        </Row>
                    </Card>
                </Col>

                <Col xs={24} xl={10}>
                    <Card title="Action Queue" extra={<Button type="link" onClick={() => navigate('/feedback')}>Open feedback</Button>} style={{ marginBottom: 16 }}>
                        {data.alerts.length > 0 ? (
                            <div>
                                {data.alerts.map((alertItem) => (
                                    <div key={`${alertItem.level}-${alertItem.title}`} style={stackRowStyle}>
                                        <Space align="start" style={{ flex: 1 }}>
                                            <WarningOutlined style={{ color: alertItem.level === 'warning' ? '#d97706' : '#2563eb', marginTop: 4 }} />
                                            <div style={textStackStyle}>
                                                <Text strong>{alertItem.title}</Text>
                                                <Text type="secondary">{alertItem.message}</Text>
                                            </div>
                                        </Space>
                                        {alertItem.href ? (
                                            <Button type="link" onClick={() => navigate(alertItem.href!)}>
                                                Open
                                            </Button>
                                        ) : null}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No immediate operational alerts" />
                        )}
                    </Card>

                    <Card title={<><FireOutlined /> Trending Queries (7 days)</>} style={{ marginBottom: 16 }}>
                        <div>
                            {data.feedback.trending_queries_7d.length > 0 ? data.feedback.trending_queries_7d.map((item, index) => (
                                <div key={`${item.question}-${index}`} style={stackRowStyle}>
                                    <Text style={{ maxWidth: '78%' }} ellipsis>
                                        {index + 1}. {item.question}
                                    </Text>
                                    <Tag>{item.count}x</Tag>
                                </div>
                            )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No trending queries yet" />}
                        </div>
                    </Card>

                    <Card title="Data Admin Coverage" extra={<Button type="link" onClick={() => navigate('/contexts')}>Open contexts</Button>}>
                        <Row gutter={[12, 12]}>
                            <Col span={12}>
                                <Statistic title="Contexts" value={data.data_admin.active_contexts} suffix={`/ ${data.data_admin.total_contexts}`} prefix={<DatabaseOutlined />} />
                            </Col>
                            <Col span={12}>
                                <Statistic title="Mappings" value={data.data_admin.total_mappings} prefix={<SyncOutlined />} />
                            </Col>
                            <Col span={12}>
                                <Statistic title="Rules" value={data.data_admin.total_rules} prefix={<SafetyCertificateOutlined />} />
                            </Col>
                            <Col span={12}>
                                <Statistic title="Schema Columns" value={data.data_admin.total_columns} prefix={<ClockCircleOutlined />} />
                            </Col>
                        </Row>

                        <div style={{ marginTop: 16 }}>
                            {[
                                `Users with admin access: ${data.data_admin.total_users}`,
                                `Active warning definitions: ${data.data_admin.active_warnings}`,
                                `Query complexity patterns: ${data.data_admin.active_patterns}`,
                                `Satisfaction trend: ${data.feedback.satisfaction_rate_30d.toFixed(1)}% in the last 30 days`,
                            ].map((item) => (
                                <div key={item} style={stackRowStyle}>
                                    <Text>{item}</Text>
                                </div>
                            ))}
                        </div>

                        <div style={{ marginTop: 16 }}>
                            <Text type="secondary">Pending reviews</Text>
                            <div style={{ marginTop: 8 }}>
                                {data.feedback.pending_review_items.length > 0 ? data.feedback.pending_review_items.map((item) => (
                                    <div key={`${item.id}-${item.created_at}`} style={stackRowStyle}>
                                        <Space orientation="vertical" size={2} style={{ width: '100%' }}>
                                            <Text ellipsis>{item.question}</Text>
                                            <Text type="secondary">{formatTimestamp(item.created_at)}</Text>
                                        </Space>
                                    </div>
                                )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No feedback waiting for review" />}
                            </div>
                        </div>
                    </Card>
                </Col>
            </Row>
        </div>
    )
}

export default Dashboard
