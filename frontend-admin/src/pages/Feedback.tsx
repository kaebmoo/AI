import React, { useState, useEffect } from 'react';
import {
    Card, Row, Col, Statistic, Table, Tag, Button, Space, Modal,
    Input, Switch, message, Spin, Typography, Tooltip
} from 'antd';
import {
    LikeOutlined, DislikeOutlined, CheckCircleOutlined,
    StarOutlined, ReloadOutlined, FireOutlined
} from '@ant-design/icons';
import { feedbackService } from '../services/feedback';
import type { FeedbackStats, PendingFeedback, TrendingQuery } from '../services/feedback';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const listRowStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    padding: '10px 0',
    borderBottom: '1px solid #f0f0f0',
};

const CATEGORY_LABELS: Record<string, { label: string; color: string }> = {
    wrong_data: { label: 'ข้อมูลไม่ถูกต้อง', color: 'red' },
    incomplete: { label: 'ไม่ครบถ้วน', color: 'orange' },
    sql_error: { label: 'SQL ผิดพลาด', color: 'volcano' },
    hard_to_understand: { label: 'เข้าใจยาก', color: 'gold' },
    slow: { label: 'ช้า', color: 'purple' },
    perfect: { label: 'ดีเยี่ยม', color: 'green' },
    other: { label: 'อื่นๆ', color: 'default' },
};

const Feedback: React.FC = () => {
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState<FeedbackStats | null>(null);
    const [pending, setPending] = useState<PendingFeedback[]>([]);
    const [trending, setTrending] = useState<TrendingQuery[]>([]);
    const [reviewModal, setReviewModal] = useState<PendingFeedback | null>(null);
    const [reviewNotes, setReviewNotes] = useState('');
    const [isGolden, setIsGolden] = useState(false);
    const [reviewing, setReviewing] = useState(false);

    const fetchData = async () => {
        try {
            setLoading(true);
            const [statsData, pendingData, trendingData] = await Promise.all([
                feedbackService.getStats(30),
                feedbackService.getPending(50),
                feedbackService.getTrending(7, 10),
            ]);
            setStats(statsData);
            setPending(pendingData);
            setTrending(trendingData);
        } catch (err: any) {
            message.error('Failed to load feedback data');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    const handleReview = async () => {
        if (!reviewModal) return;
        setReviewing(true);
        try {
            await feedbackService.reviewFeedback(reviewModal.id, {
                notes: reviewNotes || undefined,
                is_golden_example: isGolden,
            });
            message.success('Feedback reviewed successfully');
            setReviewModal(null);
            setReviewNotes('');
            setIsGolden(false);
            fetchData();
        } catch (err: any) {
            message.error('Review failed');
        } finally {
            setReviewing(false);
        }
    };

    const columns = [
        {
            title: 'Rating',
            dataIndex: 'rating',
            key: 'rating',
            width: 80,
            render: (rating: string) => (
                rating === 'thumbs_up'
                    ? <Tag color="green" icon={<LikeOutlined />}>Good</Tag>
                    : <Tag color="red" icon={<DislikeOutlined />}>Bad</Tag>
            ),
            filters: [
                { text: 'Thumbs Up', value: 'thumbs_up' },
                { text: 'Thumbs Down', value: 'thumbs_down' },
            ],
            onFilter: (value: any, record: PendingFeedback) => record.rating === value,
        },
        {
            title: 'Question',
            dataIndex: 'question',
            key: 'question',
            ellipsis: true,
            render: (text: string) => (
                <Tooltip title={text}>
                    <Text style={{ maxWidth: 300 }} ellipsis>{text}</Text>
                </Tooltip>
            ),
        },
        {
            title: 'Comment',
            dataIndex: 'feedback_text',
            key: 'feedback_text',
            ellipsis: true,
            render: (text: string | null) => text || <Text type="secondary">-</Text>,
        },
        {
            title: 'Date',
            dataIndex: 'created_at',
            key: 'created_at',
            width: 160,
            render: (date: string | null) => date ? new Date(date).toLocaleString('th-TH') : '-',
            sorter: (a: PendingFeedback, b: PendingFeedback) =>
                (a.created_at || '').localeCompare(b.created_at || ''),
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 120,
            render: (_: any, record: PendingFeedback) => (
                <Space>
                    <Button
                        size="small"
                        type="primary"
                        icon={<CheckCircleOutlined />}
                        onClick={() => {
                            setReviewModal(record);
                            setReviewNotes('');
                            setIsGolden(false);
                        }}
                    >
                        Review
                    </Button>
                </Space>
            ),
        },
    ];

    if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

    return (
        <div style={{ padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <h2 style={{ margin: 0 }}>Feedback Management</h2>
                <Button icon={<ReloadOutlined />} onClick={fetchData}>Refresh</Button>
            </div>

            {/* Stats Cards */}
            {stats && (
                <Row gutter={16} style={{ marginBottom: 24 }}>
                    <Col xs={24} md={12} xl={6}>
                        <Card>
                            <Statistic title="Total Feedback" value={stats.total_feedback} />
                        </Card>
                    </Col>
                    <Col xs={24} md={12} xl={6}>
                        <Card>
                            <Statistic
                                title="Satisfaction Rate"
                                value={stats.satisfaction_rate}
                                suffix="%"
                                precision={1}
                                styles={{ content: { color: stats.satisfaction_rate >= 70 ? '#3f8600' : '#cf1322' } }}
                            />
                        </Card>
                    </Col>
                    <Col xs={24} md={12} xl={6}>
                        <Card>
                            <Statistic
                                title="Thumbs Up"
                                value={stats.thumbs_up}
                                prefix={<LikeOutlined />}
                                styles={{ content: { color: '#3f8600' } }}
                            />
                        </Card>
                    </Col>
                    <Col xs={24} md={12} xl={6}>
                        <Card>
                            <Statistic
                                title="Pending Reviews"
                                value={stats.pending_reviews}
                                styles={{ content: { color: stats.pending_reviews > 0 ? '#cf1322' : '#3f8600' } }}
                            />
                        </Card>
                    </Col>
                </Row>
            )}

            {/* Category Breakdown */}
            {stats && stats.category_breakdown && Object.keys(stats.category_breakdown).length > 0 && (
                <Card title="Feedback Categories" size="small" style={{ marginBottom: 24 }}>
                    <Space wrap>
                        {Object.entries(stats.category_breakdown).map(([cat, count]) => {
                            const info = CATEGORY_LABELS[cat] || { label: cat, color: 'default' };
                            return (
                                <Tag key={cat} color={info.color}>
                                    {info.label}: {count}
                                </Tag>
                            );
                        })}
                    </Space>
                </Card>
            )}

            <Row gutter={[16, 16]}>
                {/* Pending Feedback Table */}
                <Col xs={24} xl={16}>
                    <Card title={`Pending Reviews (${pending.length})`}>
                        <Table
                            dataSource={pending}
                            columns={columns}
                            rowKey="id"
                            size="small"
                            pagination={{ pageSize: 10 }}
                        />
                    </Card>
                </Col>

                {/* Trending Queries */}
                <Col xs={24} xl={8}>
                    <Card
                        title={<><FireOutlined /> Trending Queries (7 days)</>}
                    >
                        {trending.length > 0 ? (
                            <div>
                                {trending.map((item, index) => (
                                    <div key={`${item.question}-${index}`} style={listRowStyle}>
                                        <Text ellipsis style={{ flex: 1 }}>
                                            <Tag color="blue">{index + 1}</Tag>
                                            {item.question}
                                        </Text>
                                        <Tag>{item.count}x</Tag>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <Text type="secondary">No trending queries</Text>
                        )}
                    </Card>
                </Col>
            </Row>

            {/* Review Modal */}
            <Modal
                title="Review Feedback"
                open={!!reviewModal}
                onCancel={() => setReviewModal(null)}
                onOk={handleReview}
                confirmLoading={reviewing}
                okText="Mark as Reviewed"
                width={700}
            >
                {reviewModal && (
                    <div>
                        <div style={{ marginBottom: 16 }}>
                            <Text strong>Rating: </Text>
                            {reviewModal.rating === 'thumbs_up'
                                ? <Tag color="green" icon={<LikeOutlined />}>Good</Tag>
                                : <Tag color="red" icon={<DislikeOutlined />}>Bad</Tag>
                            }
                        </div>

                        <div style={{ marginBottom: 16 }}>
                            <Text strong>Question:</Text>
                            <Paragraph style={{ background: '#f5f5f5', padding: 12, borderRadius: 8, marginTop: 4 }}>
                                {reviewModal.question}
                            </Paragraph>
                        </div>

                        {reviewModal.ai_response && (
                            <div style={{ marginBottom: 16 }}>
                                <Text strong>AI Response:</Text>
                                <Paragraph
                                    ellipsis={{ rows: 4, expandable: true }}
                                    style={{ background: '#f0f5ff', padding: 12, borderRadius: 8, marginTop: 4 }}
                                >
                                    {reviewModal.ai_response}
                                </Paragraph>
                            </div>
                        )}

                        {reviewModal.feedback_text && (
                            <div style={{ marginBottom: 16 }}>
                                <Text strong>User Comment:</Text>
                                <Paragraph style={{ background: '#fff7e6', padding: 12, borderRadius: 8, marginTop: 4 }}>
                                    {reviewModal.feedback_text}
                                </Paragraph>
                            </div>
                        )}

                        <div style={{ marginBottom: 16 }}>
                            <Text strong>Review Notes:</Text>
                            <TextArea
                                rows={3}
                                value={reviewNotes}
                                onChange={(e) => setReviewNotes(e.target.value)}
                                placeholder="Add review notes (optional)"
                                style={{ marginTop: 4 }}
                            />
                        </div>

                        <div>
                            <Space>
                                <Switch checked={isGolden} onChange={setIsGolden} />
                                <Text><StarOutlined /> Mark as Golden Example</Text>
                            </Space>
                            <br />
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                Golden examples are used to train the AI for better future responses
                            </Text>
                        </div>
                    </div>
                )}
            </Modal>
        </div>
    );
};

export default Feedback;
