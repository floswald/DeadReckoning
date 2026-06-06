% analysis.m — main analysis script
% Requires: Statistics and Machine Learning Toolbox, Optimization Toolbox

% Load data — absolute path (bad practice, left over from author's machine)
T = readtable('/Users/jsmith/Dropbox/JPE_paper/data/lfs_2019.csv');
T = T(~isnan(T.wage), :);

% Regression using Statistics Toolbox
lm = fitlm(T, 'wage ~ age + education');
disp(lm)

% Minimize objective using Optimization Toolbox
x0 = [0, 0];
opts = optimoptions('fmincon', 'Display', 'off');
[xopt, fval] = fmincon(@(x) sum(x.^2), x0, [], [], [], [], [], [], [], opts);

% Plot
fig = figure('Visible', 'off');
scatter(T.age, T.wage, 20, 'filled');
xlabel('Age'); ylabel('Wage');
title('Wage vs Age');

% Writes to working directory, not the figures/ folder LaTeX expects
saveas(fig, 'fig1.pdf');
