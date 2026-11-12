import { Version } from '@microsoft/sp-core-library';
import {
  type IPropertyPaneConfiguration,
  PropertyPaneTextField,
  PropertyPaneDropdown
} from '@microsoft/sp-property-pane';
import { BaseClientSideWebPart } from '@microsoft/sp-webpart-base';
import { escape } from '@microsoft/sp-lodash-subset';

import styles from './ProcessHubWebPart.module.scss';
import * as strings from 'ProcessHubWebPartStrings';

export interface IProcessHubWebPartProps {
  hubUrl: string;      // https address of the hosted MEA Process Hub, e.g. https://processhub.example.com
  startPage: string;   // view the frame opens: #/dashboard, #/handbook, #/library, #/departments or "custom"
  customPage: string;  // e.g. #/departments/LOG or #/process/WL-M-IB-01 (used when startPage is "custom")
  height: string;      // frame height in pixels on a SharePoint page (a Teams tab fills the window)
}

/**
 * Shows MEA Process Hub, which runs on the company server, inside a SharePoint page or a Microsoft Teams tab.
 * The web part contains no process data and no program logic of the tool: it is a frame around the hosted address.
 * The server must allow this site as a frame ancestor (MEA_HUB_EMBED_ORIGINS, see docs/TEAMS.md of the tool).
 */
export default class ProcessHubWebPart extends BaseClientSideWebPart<IProcessHubWebPartProps> {

  private _inTeams: boolean = false;

  protected onInit(): Promise<void> {
    this._inTeams = !!this.context.sdks.microsoftTeams;
    return Promise.resolve();
  }

  /** Only an https address without path, query or fragment is accepted; anything else shows the set-up hint. */
  private _base(): string | undefined {
    const raw: string = (this.properties.hubUrl || '').trim().replace(/\/+$/, '');
    return /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/.test(raw) ? raw : undefined;
  }

  private _target(): string {
    const page: string = this.properties.startPage === 'custom' ? (this.properties.customPage || '').trim() : (this.properties.startPage || '#/dashboard');
    return /^#\/[A-Za-z0-9._\-\/%]*$/.test(page) ? page : '#/dashboard';
  }

  public render(): void {
    const base: string | undefined = this._base();
    if (!base) {
      this.domElement.innerHTML = `
        <div class="${styles.hint}">
          <strong>${escape(strings.SetupTitle)}</strong>
          <div>${escape(strings.SetupText)}</div>
        </div>`;
      return;
    }
    const px: number = Math.min(4000, Math.max(300, parseInt(this.properties.height, 10) || 900));
    const height: string = this._inTeams ? 'calc(100vh - 8px)' : px + 'px';
    const src: string = base + '/' + this._target();
    this.domElement.innerHTML = `
      <div class="${styles.processHub}">
        <iframe class="${styles.frame}" style="height:${height}" src="${escape(src)}" title="MEA Process Hub" allow="clipboard-write"></iframe>
        <div class="${styles.foot}"><a href="${escape(src)}" target="_blank" rel="noopener noreferrer">${escape(strings.OpenInBrowser)}</a></div>
      </div>`;
  }

  protected get dataVersion(): Version {
    return Version.parse('1.0');
  }

  private _validateUrl(value: string): string {
    const v: string = (value || '').trim().replace(/\/+$/, '');
    return !v || /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/.test(v) ? '' : strings.UrlInvalid;
  }

  private _validatePage(value: string): string {
    return !value || /^#\/[A-Za-z0-9._\-\/%]*$/.test(value.trim()) ? '' : strings.PageInvalid;
  }

  protected getPropertyPaneConfiguration(): IPropertyPaneConfiguration {
    return {
      pages: [
        {
          header: { description: strings.PropertyPaneDescription },
          groups: [
            {
              groupName: strings.BasicGroupName,
              groupFields: [
                PropertyPaneTextField('hubUrl', {
                  label: strings.UrlFieldLabel,
                  placeholder: 'https://processhub.example.com',
                  onGetErrorMessage: this._validateUrl.bind(this)
                }),
                PropertyPaneDropdown('startPage', {
                  label: strings.StartFieldLabel,
                  options: [
                    { key: '#/dashboard', text: strings.StartDashboard },
                    { key: '#/handbook', text: strings.StartHandbook },
                    { key: '#/library', text: strings.StartLibrary },
                    { key: '#/departments', text: strings.StartDepartments },
                    { key: 'custom', text: strings.StartCustom }
                  ]
                }),
                PropertyPaneTextField('customPage', {
                  label: strings.CustomFieldLabel,
                  placeholder: '#/departments/LOG',
                  disabled: this.properties.startPage !== 'custom',
                  onGetErrorMessage: this._validatePage.bind(this)
                }),
                PropertyPaneTextField('height', {
                  label: strings.HeightFieldLabel
                })
              ]
            }
          ]
        }
      ]
    };
  }
}
