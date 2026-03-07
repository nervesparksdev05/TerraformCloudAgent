import React, { useState } from 'react';
import MermaidDiagram from './MermaidDiagram';

// ── Tiny helpers ────────────────────────────────────────────────────────────

const fmt = (v) => (v == null || v === '' ? '—' : String(v));
const bool = (v) => (v === true || v === 'true' || v === 1 ? '✅ Yes' : v === false || v === 'false' || v === 0 ? '❌ No' : '—');

// Known Terraform resource types → icons / labels
const RESOURCE_META = {
  aws_instance:               { icon: '🖥️',  label: 'EC2 Instance',          color: '#f59e0b' },
  aws_security_group:         { icon: '🛡️',  label: 'Security Group',        color: '#6366f1' },
  aws_vpc:                    { icon: '🌐',  label: 'VPC',                   color: '#10b981' },
  aws_subnet:                 { icon: '🔗',  label: 'Subnet',                color: '#14b8a6' },
  aws_iam_role:               { icon: '🔑',  label: 'IAM Role',              color: '#8b5cf6' },
  aws_iam_instance_profile:   { icon: '👤',  label: 'IAM Instance Profile',  color: '#a78bfa' },
  aws_iam_role_policy:        { icon: '📋',  label: 'IAM Policy',            color: '#c4b5fd' },
  aws_iam_role_policy_attachment: { icon: '📎', label: 'Policy Attachment',  color: '#ddd6fe' },
  aws_db_instance:            { icon: '🗄️',  label: 'RDS Database',          color: '#ef4444' },
  aws_elasticache_cluster:    { icon: '⚡',  label: 'ElastiCache',           color: '#f97316' },
  aws_s3_bucket:              { icon: '🪣',  label: 'S3 Bucket',             color: '#eab308' },
  aws_lb:                     { icon: '⚖️',  label: 'Load Balancer',         color: '#06b6d4' },
  aws_autoscaling_group:      { icon: '📈',  label: 'Auto Scaling Group',    color: '#84cc16' },
  aws_sns_topic:              { icon: '📣',  label: 'SNS Topic',             color: '#ec4899' },
  aws_sns_topic_subscription: { icon: '📧',  label: 'SNS Subscription',      color: '#f43f5e' },
  aws_cloudwatch_metric_alarm:{ icon: '🔔',  label: 'CloudWatch Alarm',      color: '#fb923c' },
  aws_secretsmanager_secret:  { icon: '🔐',  label: 'Secrets Manager',       color: '#7c3aed' },
  aws_route53_record:         { icon: '🌍',  label: 'Route 53',              color: '#0ea5e9' },
  aws_acm_certificate:        { icon: '📜',  label: 'ACM Certificate',       color: '#22d3ee' },
};

// Parse resource types from main.tf string
function parseResources(mainTf = '') {
  const matches = [...mainTf.matchAll(/resource\s+"(aws_[\w]+)"\s+"(\w+)"/g)];
  const counts = {};
  for (const [, rtype] of matches) {
    counts[rtype] = (counts[rtype] || 0) + 1;
  }
  return Object.entries(counts).map(([rtype, count]) => ({
    rtype, count,
    ...(RESOURCE_META[rtype] || { icon: '📦', label: rtype.replace(/^aws_/, '').replace(/_/g, ' '), color: '#6b7280' }),
  }));
}

// Cost model (monthly, USD, approximate)
const INST_COST = { 't3.micro': 7.50, 't3.small': 15.18, 't3.medium': 30.37, 't3.large': 60.74, 't3.xlarge': 121.47, 't2.micro': 8.50 };
const RDS_COST  = { 'db.t3.micro': 12.41, 'db.t3.small': 24.82, 'db.t3.medium': 49.64 };
const ELC_COST  = { 'cache.t3.micro': 12.24, 'cache.t3.small': 24.48, 'cache.t3.medium': 48.96 };

function buildCostBreakdown(cp = {}) {
  const items = [];
  const itype  = cp.instance_type || 't3.micro';
  const isProd = (cp.environment || '').toLowerCase().includes('prod');
  const icount = parseInt(cp.instance_count || 1, 10);
  const disk   = parseInt(cp.storage_size_gb || 8, 10);
  const hasALB = cp.use_alb;
  const hasDB  = cp.has_database;
  const dbHost = (cp.database_hosting_model || '').toLowerCase();
  const hasCache = cp.has_cache;
  const multiAz  = cp.enable_multi_az;

  // EC2
  if (!isProd && itype === 't3.micro' && icount <= 1) {
    items.push({ label: `EC2 (1× ${itype})`, cost: 0, badge: 'Free Tier', color: '#10b981' });
  } else {
    items.push({ label: `EC2 (${icount}× ${itype})`, cost: icount * (INST_COST[itype] || 15), color: '#f59e0b' });
  }

  // EBS
  const totalDisk = icount * disk;
  if (!isProd && totalDisk <= 30) {
    items.push({ label: `EBS (${totalDisk}GB gp2)`, cost: 0, badge: 'Free Tier', color: '#10b981' });
  } else {
    items.push({ label: `EBS (${totalDisk}GB gp2)`, cost: totalDisk * 0.10, color: '#6366f1' });
  }

  if (hasALB) items.push({ label: 'App Load Balancer', cost: 16.20, color: '#06b6d4' });

  if (hasDB && !dbHost.includes('atlas') && !dbHost.includes('external')) {
    const rdsClass = (cp.rds_config || {}).instance_class || 'db.t3.micro';
    let rds = RDS_COST[rdsClass] || 12.41;
    if (multiAz) rds *= 2;
    if (!isProd && rdsClass === 'db.t3.micro' && !multiAz) {
      items.push({ label: `RDS (${rdsClass})`, cost: 0, badge: 'Free Tier', color: '#10b981' });
    } else {
      items.push({ label: `RDS (${rdsClass}${multiAz ? ' Multi-AZ' : ''})`, cost: rds, color: '#ef4444' });
    }
  }

  if (hasCache) {
    const cClass = (cp.cache_config || {}).instance_class || 'cache.t3.micro';
    let c = ELC_COST[cClass] || 12.24;
    if (multiAz) c *= 2;
    items.push({ label: `ElastiCache (${cClass})`, cost: c, color: '#f97316' });
  }

  if (cp.custom_domain) items.push({ label: 'Route 53 Hosted Zone', cost: 0.50, color: '#0ea5e9' });
  items.push({ label: 'CloudWatch', cost: 0, badge: 'Free Tier', color: '#10b981' });

  const total = items.reduce((s, i) => s + i.cost, 0);
  return { items, total };
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ icon, label, value, sub, color = '#6366f1' }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.07)',
      borderRadius: 16,
      padding: '20px 24px',
      display: 'flex', alignItems: 'center', gap: 16,
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 12,
        background: `${color}22`, display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontSize: 20, flexShrink: 0,
      }}>
        {icon}
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>{label}</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: '#f1f5f9', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}

function CostBar({ label, cost, badge, color, max }) {
  const pct = max > 0 ? Math.max(3, (cost / max) * 100) : 3;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
      <div style={{ width: 200, fontSize: 12, color: '#9ca3af', flexShrink: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</div>
      <div style={{ flex: 1, height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%', borderRadius: 4,
          background: badge ? '#10b981' : color,
          transition: 'width 0.8s cubic-bezier(.4,0,.2,1)',
        }} />
      </div>
      <div style={{ width: 90, textAlign: 'right', fontSize: 12, fontWeight: 600, color: badge ? '#10b981' : '#f1f5f9', flexShrink: 0 }}>
        {badge ? badge : `$${cost.toFixed(2)}/mo`}
      </div>
    </div>
  );
}

function ResourceCard({ icon, label, count, color }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)',
      border: `1px solid ${color}33`,
      borderRadius: 12, padding: '14px 16px',
      display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <span style={{ fontSize: 22 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color, fontWeight: 600, marginBottom: 2 }}>{label}</div>
        <div style={{ fontSize: 10, color: '#6b7280' }}>{count} resource{count !== 1 ? 's' : ''}</div>
      </div>
      <div style={{
        background: `${color}22`, color, borderRadius: 20,
        fontSize: 11, fontWeight: 700, padding: '2px 8px',
      }}>{count}</div>
    </div>
  );
}

const SECTION = ({ title, children, icon }) => (
  <section>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
      {icon && <span style={{ fontSize: 18 }}>{icon}</span>}
      <h2 style={{ fontSize: 15, fontWeight: 700, color: '#f1f5f9', letterSpacing: '-0.01em', margin: 0 }}>{title}</h2>
    </div>
    {children}
  </section>
);

// ── Main component ────────────────────────────────────────────────────────────

export const InsightsPanel = ({ topologyDiagram, collectedParams = {}, runData = {} }) => {
  const cp    = collectedParams || {};
  const env   = (cp.environment || 'dev').toLowerCase();
  const isProd = env.includes('prod');
  const region = cp.aws_region || cp.region || 'us-east-1';
  const itype  = cp.instance_type || 't3.micro';
  const disk   = cp.storage_size_gb || 8;

  const { items: costItems, total: costTotal } = buildCostBreakdown(cp);
  const maxCost = Math.max(...costItems.map((i) => i.cost), 1);

  // Parse resources from Terraform files (passed via runData.metadata or not available)
  const mainTf = runData?.files?.main_tf || '';
  const resources = parseResources(mainTf);

  // Key config fields to display
  const configFields = [
    ['Environment',    fmt(cp.environment)],
    ['Region',         fmt(region)],
    ['Instance Type',  fmt(itype)],
    ['Disk',           `${disk} GB gp2`],
    ['SSH Key',        cp.ssh_key_name || cp.key_pair_name || '— (SSM access)'],
    ['Alert Email',    cp.alert_email || '— (disabled)'],
    ['Auto Scaling',   bool(cp.use_asg)],
    ['Load Balancer',  bool(cp.use_alb)],
    ['Multi-AZ',       bool(cp.enable_multi_az)],
    ['Database',       cp.has_database ? (cp.database_type || 'yes') : '—'],
    ['Cache',          cp.has_cache ? (cp.cache_type || 'yes') : '—'],
    ['Secrets Mgr',    bool(cp.use_secrets_manager)],
    ['Custom Domain',  cp.custom_domain || '—'],
    ['GitHub Repo',    cp.github_owner && cp.github_repo ? `${cp.github_owner}/${cp.github_repo}` : '—'],
    ['Language',       fmt(cp.language)],
  ].filter(([, v]) => v && v !== '—');

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 32, width: '100%' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 32 }}>

        {/* ── HEADER STAT CARDS ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
          <StatCard icon="🌍" label="Region"      value={region}   color="#10b981" />
          <StatCard icon="🖥️" label="Instance"    value={itype}    sub="Free Tier eligible" color="#f59e0b" />
          <StatCard icon="⚙️" label="Environment" value={isProd ? '🚀 Production' : '🧪 Development'} color={isProd ? '#ef4444' : '#6366f1'} />
          <StatCard
            icon="💰"
            label="Est. Monthly Cost"
            value={costTotal === 0 ? 'Free Tier' : `~$${costTotal.toFixed(2)}`}
            sub={costTotal === 0 ? '750 hrs × t3.micro' : 'per month'}
            color={costTotal === 0 ? '#10b981' : '#f59e0b'}
          />
          {cp.use_asg && (
            <StatCard icon="📈" label="Auto Scaling" value={`${(cp.autoscaling_config?.min_instances || 1)}–${(cp.autoscaling_config?.max_instances || 4)} servers`} color="#84cc16" />
          )}
          {cp.daily_active_users && (
            <StatCard icon="👥" label="Target DAU" value={Number(cp.daily_active_users).toLocaleString()} color="#06b6d4" />
          )}
        </div>

        {/* ── COST BREAKDOWN CHART ── */}
        <SECTION title="Monthly Cost Breakdown" icon="📊">
          <div style={{
            background: 'rgba(0,0,0,0.3)',
            border: '1px solid rgba(99,102,241,0.15)',
            borderRadius: 16, padding: 24,
          }}>
            {costItems.map((item, i) => (
              <CostBar key={i} {...item} max={maxCost} />
            ))}
            <div style={{
              borderTop: '1px solid rgba(255,255,255,0.07)',
              marginTop: 16, paddingTop: 16,
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ fontSize: 12, color: '#6b7280' }}>
                * Approximate pricing — actual costs vary by usage and region
              </span>
              <span style={{ fontSize: 15, fontWeight: 700, color: costTotal === 0 ? '#10b981' : '#f1f5f9' }}>
                Total: {costTotal === 0 ? '✅ $0.00 Free Tier' : `~$${costTotal.toFixed(2)}/mo`}
              </span>
            </div>
          </div>
        </SECTION>

        {/* ── ARCHITECTURE RESOURCE MAP ── */}
        <SECTION title="Infrastructure Architecture" icon="🏗️">
          <div style={{
            background: 'rgba(0,0,0,0.3)',
            border: '1px solid rgba(99,102,241,0.15)',
            borderRadius: 16, padding: 24,
          }}>
            {/* Always-present base layer */}
            <InfraLayer label="Network Layer" color="#10b981">
              <InfraBox icon="🌐" title="Default VPC" sub={region} color="#10b981" />
              <InfraBox icon="🔗" title="Subnet" sub={`${region}a`} color="#14b8a6" />
              <InfraBox icon="🛡️" title="Security Group" sub="Ports 22, 80, 5000" color="#6366f1" />
              {cp.use_alb && <InfraBox icon="⚖️" title="Application LB" sub="Public, HTTPS" color="#06b6d4" />}
            </InfraLayer>

            <Arrow />

            <InfraLayer label="Compute Layer" color="#f59e0b">
              <InfraBox icon="🖥️" title={`EC2 ${itype}`} sub={`${disk}GB gp2 · Ubuntu 22.04`} color="#f59e0b" />
              {cp.use_asg && (
                <InfraBox icon="📈" title="Auto Scaling Group"
                  sub={`${cp.autoscaling_config?.min_instances || 1}–${cp.autoscaling_config?.max_instances || 4} instances`}
                  color="#84cc16" />
              )}
              <InfraBox icon="🔑" title="IAM Role" sub="EC2 instance profile" color="#8b5cf6" />
            </InfraLayer>

            {(cp.has_database || cp.has_cache || cp.use_secrets_manager || cp.storage_needs) && (
              <>
                <Arrow />
                <InfraLayer label="Data Layer" color="#ef4444">
                  {cp.has_database && <InfraBox icon="🗄️" title={cp.database_type || 'Database'} sub={`${cp.rds_config?.instance_class || 'db.t3.micro'}${cp.enable_multi_az ? ' · Multi-AZ' : ''}`} color="#ef4444" />}
                  {cp.has_cache && <InfraBox icon="⚡" title={cp.cache_type || 'Cache'} sub={cp.cache_config?.instance_class || 'cache.t3.micro'} color="#f97316" />}
                  {cp.use_secrets_manager && <InfraBox icon="🔐" title="Secrets Manager" sub="Encrypted secrets" color="#7c3aed" />}
                  {cp.storage_needs && <InfraBox icon="🪣" title="S3 Bucket" sub="Object storage" color="#eab308" />}
                </InfraLayer>
              </>
            )}

            <Arrow />

            <InfraLayer label="Observability Layer" color="#ec4899">
              <InfraBox icon="🔔" title="CloudWatch Alarm" sub="CPU ≥ 80%" color="#fb923c" />
              <InfraBox icon="📣" title="SNS Topic" sub={cp.alert_email || 'No email set'} color="#ec4899" />
              {cp.custom_domain && <InfraBox icon="🌍" title="Route 53" sub={cp.custom_domain} color="#0ea5e9" />}
            </InfraLayer>
          </div>
        </SECTION>

        {/* ── TOPOLOGY MERMAID (if available) ── */}
        <SECTION title="Topology Diagram" icon="🔀">
          <div style={{
            background: 'rgba(0,0,0,0.3)',
            border: '1px solid rgba(99,102,241,0.15)',
            borderRadius: 16, padding: 24,
            minHeight: 200, position: 'relative', overflow: 'hidden',
          }}>
            <div style={{
              position: 'absolute', inset: '0 0 auto 0', height: 120,
              background: 'radial-gradient(ellipse at center, rgba(99,102,241,0.08) 0%, transparent 70%)',
              pointerEvents: 'none',
            }} />
            {topologyDiagram ? (
              <div style={{ position: 'relative', zIndex: 1 }}>
                <MermaidDiagram chart={topologyDiagram} />
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 160, color: '#4b5563', fontSize: 13, gap: 8 }}>
                <span style={{ fontSize: 32 }}>🗺️</span>
                No topology diagram generated yet.<br />
                <span style={{ fontSize: 11 }}>It appears after deploy completes.</span>
              </div>
            )}
          </div>
        </SECTION>

        {/* ── CONFIGURATION SUMMARY ── */}
        <SECTION title="Configuration Summary" icon="📋">
          <div style={{
            background: 'rgba(0,0,0,0.3)',
            border: '1px solid rgba(99,102,241,0.15)',
            borderRadius: 16, padding: 24,
            display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0 32px',
          }}>
            {configFields.map(([label, value]) => (
              <div key={label} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.05)',
              }}>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{label}</span>
                <span style={{ fontSize: 12, color: '#e2e8f0', fontFamily: 'monospace', textAlign: 'right', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</span>
              </div>
            ))}
          </div>
        </SECTION>

      </div>
    </div>
  );
};

// ── Architecture Diagram helpers ──────────────────────────────────────────────

function InfraLayer({ label, color, children }) {
  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 600, color, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 10 }}>{label}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        {children}
      </div>
    </div>
  );
}

function InfraBox({ icon, title, sub, color }) {
  return (
    <div style={{
      background: `${color}11`,
      border: `1px solid ${color}44`,
      borderRadius: 10, padding: '12px 16px', minWidth: 150,
      display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      <span style={{ fontSize: 20 }}>{icon}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: '#e2e8f0' }}>{title}</span>
      <span style={{ fontSize: 10, color: '#6b7280' }}>{sub}</span>
    </div>
  );
}

function Arrow() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', padding: '8px 0', color: '#374151' }}>
      <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }} />
      <span style={{ fontSize: 12, margin: '0 8px', color: '#4b5563' }}>▼</span>
      <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }} />
    </div>
  );
}

export default InsightsPanel;
