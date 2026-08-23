import { Button, Dropdown, Field, Input, Option, Spinner } from "@fluentui/react-components";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { platformApi } from "../api/platformApi";
import type {
  PlatformAssociationMember,
  PlatformAssociationSummary,
  PlatformEnterprise,
} from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import styles from "./PlatformAssociationsPage.module.css";

type MemberDraft = PlatformAssociationMember & { draftTier: string; draftSeats: number };

export function PlatformAssociationsPage() {
  const [associations, setAssociations] = useState<PlatformAssociationSummary[]>([]);
  const [enterprises, setEnterprises] = useState<PlatformEnterprise[]>([]);
  const [associationId, setAssociationId] = useState("");
  const [members, setMembers] = useState<MemberDraft[]>([]);
  const [newCompanyId, setNewCompanyId] = useState("");
  const [newTier, setNewTier] = useState("");
  const [newSeats, setNewSeats] = useState(0);
  const [loading, setLoading] = useState(true);
  const [membersLoading, setMembersLoading] = useState(false);
  const [busyId, setBusyId] = useState<string>();
  const [error, setError] = useState<ApiError>();
  const [success, setSuccess] = useState<string>();

  useEffect(() => {
    let active = true;
    void Promise.all([
      platformApi.listAssociations(),
      platformApi.listEnterprises({ limit: 100 }),
    ]).then(([nextAssociations, nextEnterprises]) => {
      if (!active) return;
      setAssociations(nextAssociations);
      setEnterprises(nextEnterprises);
      setAssociationId(nextAssociations[0]?.companyId ?? "");
    }).catch((caught) => {
      if (active) setError(caught instanceof ApiError ? caught : new ApiError("协会治理数据加载失败。", { code: "UNKNOWN_ERROR" }));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const loadAssociations = async () => {
    const rows = await platformApi.listAssociations();
    setAssociations(rows);
  };

  const loadMembers = async (nextAssociationId: string) => {
    if (!nextAssociationId) { setMembers([]); return; }
    setMembersLoading(true); setError(undefined);
    try {
      const rows = await platformApi.listAssociationMembers(nextAssociationId);
      setMembers(rows.map((row) => ({ ...row, draftTier: row.memberTier ?? "", draftSeats: row.allocatedSeats })));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("协会成员加载失败。", { code: "UNKNOWN_ERROR" }));
    } finally { setMembersLoading(false); }
  };

  useEffect(() => { void loadMembers(associationId); }, [associationId]);

  const availableEnterprises = useMemo(() => {
    const existing = new Set(members.map((member) => member.companyId));
    return enterprises.filter((company) => company.subjectType !== "association" && !existing.has(company.companyId));
  }, [enterprises, members]);
  const selectedEnterprise = availableEnterprises.find((company) => company.companyId === newCompanyId);

  const saveMember = async (member: MemberDraft) => {
    setBusyId(member.companyId); setError(undefined); setSuccess(undefined);
    try {
      await platformApi.upsertAssociationMember(associationId, member.companyId, {
        expectedVersion: member.version,
        memberTier: member.draftTier,
        allocatedSeats: member.draftSeats,
        benefits: member.benefits,
      });
      await Promise.all([loadMembers(associationId), loadAssociations()]);
      setSuccess(`已更新 ${member.legalName} 的会员范围。`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("成员更新失败。", { code: "UNKNOWN_ERROR" }));
    } finally { setBusyId(undefined); }
  };

  const addMember = async () => {
    if (!associationId || !newCompanyId) return;
    setBusyId(newCompanyId); setError(undefined); setSuccess(undefined);
    try {
      await platformApi.upsertAssociationMember(associationId, newCompanyId, {
        expectedVersion: 0, memberTier: newTier, allocatedSeats: newSeats,
      });
      setNewCompanyId(""); setNewTier(""); setNewSeats(0);
      await Promise.all([loadMembers(associationId), loadAssociations()]);
      setSuccess("成员企业已加入协会范围。");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("添加成员失败。", { code: "UNKNOWN_ERROR" }));
    } finally { setBusyId(undefined); }
  };

  const removeMember = async (member: MemberDraft) => {
    if (!window.confirm(`确定将「${member.legalName}」从当前协会范围移除？企业自身数据不会被删除。`)) return;
    setBusyId(member.companyId); setError(undefined); setSuccess(undefined);
    try {
      await platformApi.removeAssociationMember(associationId, member.companyId, member.version);
      await Promise.all([loadMembers(associationId), loadAssociations()]);
      setSuccess("成员关系已移除，企业租户与数据保持不变。");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("移除成员失败。", { code: "UNKNOWN_ERROR" }));
    } finally { setBusyId(undefined); }
  };

  if (loading) return <main className="page-stack"><PageHeader title="协会与商会" description="管理跨企业范围，不改变企业的数据隔离边界。" /><ResourceState status="loading" /></main>;
  if (error && associations.length === 0) return <main className="page-stack"><PageHeader title="协会与商会" description="管理跨企业范围。" /><ResourceState status="error" title={error.message} errorCode={error.code} /></main>;

  return <main className="page-stack">
    <PageHeader title="协会与商会" description="平台只管理成员范围、会员等级、名额和权益元数据；成员企业仍然是独立租户。" />
    <FormFeedback success={success} error={error} />
    {associations.length === 0 ? <section className="content-panel"><ResourceState status="empty" title="暂无协会主体" description="先在企业中心创建主体类型为“协会/商会”的企业身份。" /></section> : <>
      <section className="content-panel">
        <div className="form-section-heading"><div><h2>管理范围</h2><p>选择一个协会主体查看和维护其成员企业。</p></div></div>
        <div className={styles.summaryGrid}>{associations.map((association) => <button type="button" className={styles.summaryCard} data-selected={association.companyId === associationId} key={association.companyId} onClick={() => setAssociationId(association.companyId)}><strong>{association.shortName ?? association.legalName}</strong><span>{association.memberCount} 家成员 · {association.allocatedSeats} 个名额</span><small>{association.businessTenantKey}</small></button>)}</div>
      </section>
      <section className="content-panel">
        <div className="form-section-heading"><div><h2>添加成员企业</h2><p>只建立治理关系，不转移租户归属，不开放企业私有内容。</p></div></div>
        <div className={styles.addPanel}>
          <Field label="成员企业"><Dropdown value={selectedEnterprise?.companyName ?? ""} selectedOptions={newCompanyId ? [newCompanyId] : []} placeholder="选择独立企业" onOptionSelect={(_, data) => setNewCompanyId(data.optionValue ?? "")}>{availableEnterprises.map((company) => <Option key={company.companyId} value={company.companyId} text={company.companyName}>{company.companyName}</Option>)}</Dropdown></Field>
          <Field label="会员等级"><Input value={newTier} onChange={(_, data) => setNewTier(data.value)} placeholder="例如：理事单位" /></Field>
          <Field label="分配名额"><Input type="number" min={0} value={String(newSeats)} onChange={(_, data) => setNewSeats(Math.max(0, Number(data.value) || 0))} /></Field>
          <Button appearance="primary" disabled={!newCompanyId || busyId === newCompanyId} onClick={() => void addMember()}>{busyId === newCompanyId ? "正在添加" : "添加成员"}</Button>
        </div>
      </section>
      <section className="content-panel">
        <div className="form-section-heading"><div><h2>当前成员</h2><p>移除关系不会删除成员企业或其任何数据。</p></div></div>
        {membersLoading ? <Spinner label="正在加载成员" /> : members.length === 0 ? <ResourceState status="empty" title="尚未添加成员" /> : <div className={styles.memberList}>{members.map((member) => <article className={styles.memberCard} key={member.id}>
          <div className={styles.memberIdentity}><strong>{member.shortName ?? member.legalName}</strong><span className={styles.memberMeta}>{member.businessTenantKey}</span></div>
          <Field label="会员等级"><Input value={member.draftTier} onChange={(_, data) => setMembers((current) => current.map((row) => row.id === member.id ? { ...row, draftTier: data.value } : row))} /></Field>
          <Field label="分配名额"><Input type="number" min={0} value={String(member.draftSeats)} onChange={(_, data) => setMembers((current) => current.map((row) => row.id === member.id ? { ...row, draftSeats: Math.max(0, Number(data.value) || 0) } : row))} /></Field>
          <div className={styles.actions}><Button disabled={busyId === member.companyId} onClick={() => void saveMember(member)}>保存</Button><Button appearance="subtle" disabled={busyId === member.companyId} onClick={() => void removeMember(member)}>移除</Button></div>
        </article>)}</div>}
      </section>
    </>}
  </main>;
}
