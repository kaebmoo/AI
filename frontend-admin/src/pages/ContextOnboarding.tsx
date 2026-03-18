/**
 * Context Onboarding Page
 * =======================
 * Wizard for auto-analyzing views/tables and generating NL-to-SQL config using LLM.
 * Steps: Select View → Inspect → AI Analysis & Preview → Results
 */
import React, { useState, useEffect } from 'react';
import {
    Typography, Steps, Select, Button, Card, Alert, Space,
    message, Table, Tag, Descriptions, Collapse, Spin, Badge, Result
} from 'antd';
import {
    RocketOutlined,
    SearchOutlined,
    RobotOutlined,
    CheckCircleOutlined,
    WarningOutlined,
    DatabaseOutlined,
    ReloadOutlined,
    EyeOutlined,
    ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
    onboardingService,
    type AvailableView,
    type InspectionDetail,
    type OnboardingResponse,
    type ApplySqlResponse,
} from '../services/onboardingService';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { Panel } = Collapse;

const ContextOnboarding: React.FC = () => {
    const navigate = useNavigate();
    const [currentStep, setCurrentStep] = useState(0);
    const [loading, setLoading] = useState(false);
    const [aiLoading, setAiLoading] = useState(false);

    // Step 1: View selection
    const [unconfiguredViews, setUnconfiguredViews] = useState<AvailableView[]>([]);
    const [configuredViews, setConfiguredViews] = useState<AvailableView[]>([]);
    const [selectedView, setSelectedView] = useState<string>('');

    // Step 2: Inspection
    const [inspectionData, setInspectionData] = useState<InspectionDetail | null>(null);
    const [selectedProvider, setSelectedProvider] = useState<string>('');

    // Step 3: Analysis & Config (dry-run)
    const [onboardResult, setOnboardResult] = useState<OnboardingResponse | null>(null);

    // Step 4: Apply result
    const [applyResult, setApplyResult] = useState<ApplySqlResponse | null>(null);

    // Error
    const [error, setError] = useState<string | null>(null);

    // Fetch available views on mount
    useEffect(() => {
        fetchViews();
    }, []);

    const fetchViews = async () => {
        try {
            setLoading(true);
            const data = await onboardingService.getAvailableViews();
            setUnconfiguredViews(data.unconfigured || []);
            setConfiguredViews(data.configured || []);
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Failed to load views');
        } finally {
            setLoading(false);
        }
    };

    const next = () => setCurrentStep(currentStep + 1);
    const prev = () => setCurrentStep(currentStep - 1);

    // ============================================================
    // Step 1: Select View
    // ============================================================
    const handleInspect = async () => {
        if (!selectedView) {
            message.warning('Please select a view first');
            return;
        }
        try {
            setLoading(true);
            setError(null);
            const result = await onboardingService.inspect(selectedView);
            setInspectionData(result.inspection);
            next();
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Inspection failed');
        } finally {
            setLoading(false);
        }
    };

    const renderStep1 = () => (
        <Card title={<><DatabaseOutlined /> Select View / Table</>}>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
                <div>
                    <Text strong>Choose a view or table to onboard:</Text>
                    <Select
                        showSearch
                        style={{ width: '100%', marginTop: 8 }}
                        placeholder="Select a view or table..."
                        value={selectedView || undefined}
                        onChange={(val) => setSelectedView(val)}
                        optionFilterProp="label"
                        size="large"
                    >
                        {unconfiguredViews.length > 0 && (
                            <Select.OptGroup label="Unconfigured (Recommended)">
                                {unconfiguredViews.map(v => (
                                    <Option key={v.name} value={v.name} label={v.name}>
                                        <Space>
                                            <Badge status="success" />
                                            <span>{v.name}</span>
                                            <Tag color="green">{v.type}</Tag>
                                            {v.row_count !== null && (
                                                <Text type="secondary">{v.row_count.toLocaleString()} rows</Text>
                                            )}
                                        </Space>
                                    </Option>
                                ))}
                            </Select.OptGroup>
                        )}
                        {configuredViews.length > 0 && (
                            <Select.OptGroup label="Already Configured (Re-onboard)">
                                {configuredViews.map(v => (
                                    <Option key={v.name} value={v.name} label={v.name}>
                                        <Space>
                                            <Badge status="warning" />
                                            <span>{v.name}</span>
                                            <Tag color="orange">{v.type}</Tag>
                                            {v.row_count !== null && (
                                                <Text type="secondary">{v.row_count.toLocaleString()} rows</Text>
                                            )}
                                        </Space>
                                    </Option>
                                ))}
                            </Select.OptGroup>
                        )}
                    </Select>
                </div>

                <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    onClick={handleInspect}
                    loading={loading}
                    disabled={!selectedView}
                    size="large"
                >
                    Inspect
                </Button>
            </Space>
        </Card>
    );

    // ============================================================
    // Step 2: Inspection Results
    // ============================================================
    const handleAnalyze = async () => {
        try {
            setAiLoading(true);
            setError(null);
            const result = await onboardingService.onboard({
                view_name: selectedView,
                dry_run: true,
                provider: selectedProvider || undefined,
            });
            setOnboardResult(result);
            next();
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Analysis failed');
        } finally {
            setAiLoading(false);
        }
    };

    const structureColor = (s: string) => {
        switch (s) {
            case 'long_table': return 'green';
            case 'semi_crosstab': return 'orange';
            case 'wide_table': return 'blue';
            default: return 'default';
        }
    };

    const renderStep2 = () => {
        if (!inspectionData) return null;

        const columnTableData = inspectionData.columns.map((col, idx) => ({
            key: idx,
            ...col,
        }));

        return (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Card title="Inspection Results" size="small">
                    <Descriptions bordered size="small" column={3}>
                        <Descriptions.Item label="View Name">{inspectionData.view_name}</Descriptions.Item>
                        <Descriptions.Item label="Row Count">
                            {inspectionData.row_count?.toLocaleString() || 'N/A'}
                        </Descriptions.Item>
                        <Descriptions.Item label="Structure">
                            <Tag color={structureColor(inspectionData.detected_structure)}>
                                {inspectionData.detected_structure}
                            </Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="Columns">{inspectionData.columns.length}</Descriptions.Item>
                        <Descriptions.Item label="Quality Issues">
                            {inspectionData.quality_issues.length > 0 ? (
                                <Tag color="red">{inspectionData.quality_issues.length} issues</Tag>
                            ) : (
                                <Tag color="green">None</Tag>
                            )}
                        </Descriptions.Item>
                    </Descriptions>
                </Card>

                {inspectionData.cross_column_analyses?.some(c => c.likely_semi_crosstab) && (
                    <Alert
                        message="Semi-Crosstab Detected"
                        description="This view contains columns with mixed positive/negative values. The AI will generate rules to prevent blind SUM aggregation."
                        type="warning"
                        showIcon
                        icon={<WarningOutlined />}
                    />
                )}

                <Card title="Columns" size="small">
                    <Table
                        dataSource={columnTableData}
                        size="small"
                        pagination={false}
                        scroll={{ y: 300 }}
                        columns={[
                            { title: 'Name', dataIndex: 'name', key: 'name', width: 200 },
                            { title: 'Type', dataIndex: 'type', key: 'type', width: 100 },
                            {
                                title: 'Distinct', dataIndex: 'distinct_count', key: 'distinct',
                                width: 80, render: (v: number) => v?.toLocaleString()
                            },
                            {
                                title: 'Flags', key: 'flags', width: 200,
                                render: (_: any, record: any) => (
                                    <Space size={2} wrap>
                                        {record.is_numeric && <Tag color="blue">NUMERIC</Tag>}
                                        {record.is_time_column && <Tag color="purple">TIME</Tag>}
                                        {record.has_numeric_prefix && <Tag color="cyan">PREFIX</Tag>}
                                    </Space>
                                )
                            },
                            {
                                title: 'Samples', dataIndex: 'sample_values', key: 'samples',
                                ellipsis: true,
                                render: (vals: string[]) => vals?.slice(0, 3).join(', ') || '-'
                            },
                        ]}
                    />
                </Card>

                {inspectionData.quality_issues.length > 0 && (
                    <Card title="Quality Issues" size="small">
                        {inspectionData.quality_issues.map((issue, idx) => (
                            <Alert
                                key={idx}
                                message={`${issue.column}: ${issue.type}`}
                                description={issue.description}
                                type="warning"
                                style={{ marginBottom: 8 }}
                                showIcon
                            />
                        ))}
                    </Card>
                )}

                <Card title="AI Analysis" size="small">
                    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                        <div>
                            <Text strong>Select AI Provider (optional):</Text>
                            <Select
                                style={{ width: '100%', marginTop: 8 }}
                                placeholder="Use default provider"
                                value={selectedProvider || undefined}
                                onChange={(val) => setSelectedProvider(val)}
                                allowClear
                            >
                                <Option value="gemini">Gemini</Option>
                                <Option value="claude">Claude</Option>
                                <Option value="matcha">Matcha (NT Gateway)</Option>
                            </Select>
                        </div>

                        <Space>
                            <Button onClick={prev}>Back</Button>
                            <Button
                                type="primary"
                                icon={<RobotOutlined />}
                                onClick={handleAnalyze}
                                loading={aiLoading}
                                size="large"
                            >
                                {aiLoading ? 'Analyzing with AI...' : 'Analyze with AI'}
                            </Button>
                        </Space>

                        {aiLoading && (
                            <Alert
                                message="AI Analysis in Progress"
                                description="This may take 10-30 seconds depending on the view size and AI provider."
                                type="info"
                                showIcon
                                icon={<Spin size="small" />}
                            />
                        )}
                    </Space>
                </Card>
            </Space>
        );
    };

    // ============================================================
    // Step 3: AI Analysis & Preview (dry-run result)
    // ============================================================
    const handleApply = async () => {
        // BUG-1 FIX: Apply cached SQL statements instead of re-running LLM
        const sqlStatements = onboardResult?.config?.sql_statements;
        if (!sqlStatements || sqlStatements.length === 0) {
            setError('No SQL statements to apply. Please re-run analysis.');
            return;
        }
        try {
            setLoading(true);
            setError(null);
            const result = await onboardingService.applySql(selectedView, sqlStatements);
            setApplyResult(result);
            next();
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Apply failed');
        } finally {
            setLoading(false);
        }
    };

    const renderStep3 = () => {
        if (!onboardResult) return null;

        const { analysis, config } = onboardResult;

        return (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                {/* Context Info — BUG-3 FIX: use correct field names */}
                {analysis?.context && (
                    <Card title="Context Configuration" size="small">
                        <Descriptions bordered size="small" column={2}>
                            <Descriptions.Item label="Name">
                                {analysis.context.name || '-'}
                            </Descriptions.Item>
                            <Descriptions.Item label="Display Name">
                                {analysis.context.display_name_th || analysis.context.display_name || '-'}
                            </Descriptions.Item>
                            <Descriptions.Item label="Keywords" span={2}>
                                {(analysis.context.keywords || analysis.context.detection_keywords)?.join(', ') || '-'}
                            </Descriptions.Item>
                        </Descriptions>
                    </Card>
                )}

                {analysis && (
                    <Card title="Generated Config Summary" size="small">
                        <Space size="large">
                            <Tag color="blue" style={{ fontSize: 14, padding: '4px 12px' }}>
                                {analysis.rules_count} Business Rules
                            </Tag>
                            <Tag color="green" style={{ fontSize: 14, padding: '4px 12px' }}>
                                {analysis.examples_count} Golden Examples
                            </Tag>
                            <Tag color="purple" style={{ fontSize: 14, padding: '4px 12px' }}>
                                {analysis.mappings_count} Semantic Mappings
                            </Tag>
                        </Space>
                    </Card>
                )}

                {/* Data Structure — BUG-3 FIX: use explanation field */}
                {analysis?.data_structure && (
                    <Card title="Data Structure" size="small">
                        <Descriptions bordered size="small" column={2}>
                            <Descriptions.Item label="Type">
                                <Tag color={structureColor(analysis.data_structure.type || '')}>
                                    {analysis.data_structure.type || 'unknown'}
                                </Tag>
                            </Descriptions.Item>
                            <Descriptions.Item label="Description">
                                {analysis.data_structure.explanation || analysis.data_structure.description || '-'}
                            </Descriptions.Item>
                        </Descriptions>
                    </Card>
                )}

                {config?.sql_statements && config.sql_statements.length > 0 && (
                    <Collapse>
                        <Panel
                            header={<><EyeOutlined /> SQL Preview ({config.sql_count} statements)</>}
                            key="sql"
                        >
                            <pre style={{
                                background: '#f5f5f5',
                                padding: 16,
                                borderRadius: 6,
                                maxHeight: 400,
                                overflow: 'auto',
                                fontSize: 12,
                                whiteSpace: 'pre-wrap',
                            }}>
                                {config.sql_statements.join('\n\n---\n\n')}
                            </pre>
                        </Panel>
                    </Collapse>
                )}

                {config?.summary && (
                    <Collapse>
                        <Panel header="Config Summary (Markdown)" key="summary">
                            <pre style={{
                                background: '#f9f9f9',
                                padding: 16,
                                borderRadius: 6,
                                maxHeight: 300,
                                overflow: 'auto',
                                fontSize: 12,
                                whiteSpace: 'pre-wrap',
                            }}>
                                {config.summary}
                            </pre>
                        </Panel>
                    </Collapse>
                )}

                <Space>
                    <Button onClick={prev}>Back</Button>
                    <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        onClick={handleApply}
                        loading={loading}
                        size="large"
                        danger
                    >
                        Apply Config to Database
                    </Button>
                </Space>

                <Alert
                    message="This will insert/replace config in the database"
                    description="Existing config for this view will be overwritten. SQL statements from the preview above will be applied directly (no re-analysis)."
                    type="warning"
                    showIcon
                />
            </Space>
        );
    };

    // ============================================================
    // Step 4: Results
    // ============================================================
    const renderStep4 = () => {
        if (!applyResult) return null;

        const isSuccess = applyResult.status === 'applied';
        const applyInfo = applyResult.apply || {};

        return (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Result
                    status={isSuccess ? 'success' : 'warning'}
                    title={isSuccess ? 'Config Applied Successfully' : 'Apply Failed'}
                    subTitle={`View: ${selectedView}`}
                />

                <Card title="Apply Results" size="small">
                    <Descriptions bordered size="small" column={2}>
                        <Descriptions.Item label="Status">{applyInfo.status || '-'}</Descriptions.Item>
                        <Descriptions.Item label="Successful SQL">
                            {applyInfo.success || 0}
                        </Descriptions.Item>
                        {applyInfo.errors?.length > 0 && (
                            <Descriptions.Item label="Errors" span={2}>
                                <Tag color="red">{applyInfo.errors.length} errors</Tag>
                            </Descriptions.Item>
                        )}
                    </Descriptions>
                </Card>

                {applyResult.validation && (
                    <Card
                        title={
                            <Space>
                                {applyResult.validation.passed ?
                                    <CheckCircleOutlined style={{ color: '#52c41a' }} /> :
                                    <WarningOutlined style={{ color: '#faad14' }} />
                                }
                                Validation Results
                            </Space>
                        }
                        size="small"
                    >
                        <Tag color={applyResult.validation.passed ? 'green' : 'red'}>
                            {applyResult.validation.passed ? 'PASSED' : 'ISSUES FOUND'}
                        </Tag>
                        {applyResult.validation.issues?.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                                {applyResult.validation.issues.map((issue, idx) => (
                                    <Alert
                                        key={idx}
                                        message={issue}
                                        type="warning"
                                        style={{ marginBottom: 4 }}
                                        showIcon
                                    />
                                ))}
                            </div>
                        )}
                    </Card>
                )}

                {/* BUG-4 FIX: use navigate() instead of window.location.href */}
                <Space>
                    <Button
                        type="primary"
                        icon={<DatabaseOutlined />}
                        onClick={() => navigate('/contexts')}
                    >
                        Go to Data Contexts
                    </Button>
                    <Button
                        icon={<ReloadOutlined />}
                        onClick={() => {
                            setCurrentStep(0);
                            setSelectedView('');
                            setInspectionData(null);
                            setOnboardResult(null);
                            setApplyResult(null);
                            setError(null);
                            fetchViews();
                        }}
                    >
                        Onboard Another View
                    </Button>
                </Space>
            </Space>
        );
    };

    // ============================================================
    // Main Render
    // ============================================================
    const stepItems = [
        { title: 'Select View', icon: <DatabaseOutlined /> },
        { title: 'Inspect', icon: <SearchOutlined /> },
        { title: 'AI Analysis', icon: <RobotOutlined /> },
        { title: 'Results', icon: <CheckCircleOutlined /> },
    ];

    {/* BUG-5 FIX: use <div> instead of <Layout> to avoid double wrapper */}
    return (
        <div style={{ padding: 24 }}>
            <Title level={2}>
                <RocketOutlined /> Context Onboarding
            </Title>
            <Paragraph type="secondary">
                Auto-analyze a view/table and generate all NL-to-SQL configuration using AI.
            </Paragraph>

            {error && (
                <Alert
                    message="Error"
                    description={error}
                    type="error"
                    showIcon
                    closable
                    onClose={() => setError(null)}
                    style={{ marginBottom: 16 }}
                />
            )}

            <Steps
                current={currentStep}
                items={stepItems}
                style={{ marginBottom: 24 }}
            />

            <div style={{ maxWidth: 1000 }}>
                {currentStep === 0 && renderStep1()}
                {currentStep === 1 && renderStep2()}
                {currentStep === 2 && renderStep3()}
                {currentStep === 3 && renderStep4()}
            </div>
        </div>
    );
};

export default ContextOnboarding;
