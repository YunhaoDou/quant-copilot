"use client";
import {useMemo} from "react";
import {CartesianGrid,Legend,Line,LineChart,ResponsiveContainer,Tooltip,XAxis,YAxis} from "recharts";
import type {LegacySimCurve,LegacySimStanding} from "@/lib/api";
const LINE_COLORS=["#0f766e","#2563eb","#d97706","#9333ea","#b91c1c"];
function curveKey(account: string) {
  return account.replace(/^sim-/, "");
}

function buildChartData(curves: LegacySimCurve[]) {
  const byDate = new Map<string, Record<string, number | string>>();
  for (const curve of curves) {
    for (const point of curve.series) {
      const row = byDate.get(point.date) ?? { date: point.date };
      row[curveKey(curve.account)] = point.equity;
      byDate.set(point.date, row);
    }
  }
  return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}


export default function LegacySimChart({curves,rows,selectedAccount}:{curves:LegacySimCurve[];rows:LegacySimStanding[];selectedAccount:string}){
 const chartData=useMemo(()=>buildChartData(curves),[curves]);
 const curveAccounts=curves.map(curve=>curve.account);
 const labelOf=(account:string)=>rows.find(row=>row.account===account)?.label??account;
 return (<div className="mt-4 h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                      <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                      <Tooltip />
                      <Legend formatter={(value) => labelOf(`sim-${value}`)} />
                      {curveAccounts.map((account, index) => (
                        <Line
                          key={account}
                          type="monotone"
                          dataKey={curveKey(account)}
                          name={curveKey(account)}
                          stroke={LINE_COLORS[index % LINE_COLORS.length]}
                          strokeWidth={account === selectedAccount ? 2.5 : 1.2}
                          dot={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>);
}
